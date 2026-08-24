import re
import shutil
import unicodedata
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

import uvicorn
from fastapi import FastAPI, HTTPException, Query, status
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .archive import ArchiveManager
from .config import Settings
from .models import (
    ArchiveStatus,
    ChapterRecord,
    CreateJob,
    CreateVoice,
    Job,
    StorageEntry,
    SynthesisMode,
    Voice,
    VoiceStatus,
)
from .pipeline import Pipeline, WorkerPool
from .store import JobStore


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    settings.prepare()
    store = JobStore(settings.database_path)
    workers = WorkerPool(Pipeline(settings, store), settings.worker_count)
    archives = ArchiveManager(
        settings.data_dir,
        settings.ffmpeg_command,
        settings.mp3_bitrate,
        settings.mp3_workers,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        workers.start()
        for job_id in store.recover_interrupted():
            workers.submit(job_id)
        for voice_id in store.recover_interrupted_voices():
            workers.submit_voice(voice_id)
        yield
        workers.stop()

    app = FastAPI(title="Audiobook Generator", version="0.1.0", lifespan=lifespan)
    app.state.store = store
    app.state.workers = workers

    static_dir = Path(__file__).parent / "static" / "dist"
    app.mount("/static", StaticFiles(directory=static_dir, check_dir=False), name="static")

    def stream_file(path: Path, media_type: str, filename: str) -> StreamingResponse:
        async def chunks():
            with path.open("rb") as source:
                while chunk := source.read(1024 * 1024):
                    yield chunk

        return StreamingResponse(
            chunks(),
            media_type=media_type,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    def archive_filename(title: str | None, output_format: str) -> str:
        normalized = unicodedata.normalize("NFKD", title or "")
        ascii_title = normalized.encode("ascii", "ignore").decode("ascii").lower()
        slug = re.sub(r"[^a-z0-9]+", "-", ascii_title).strip("-")[:100].rstrip("-")
        return f"{slug or 'audiobook'}-{output_format}.zip"

    @app.get("/", include_in_schema=False)
    async def index() -> FileResponse:
        index_file = static_dir / "index.html"
        if not index_file.is_file():
            raise HTTPException(
                status_code=503,
                detail=(
                    "The frontend has not been built. Run `cd frontend && npm install && "
                    "npm run build`, or use `npm run dev` and open http://127.0.0.1:5173."
                ),
            )
        return FileResponse(index_file)

    @app.get("/api/health")
    async def health() -> dict[str, str | bool]:
        return {
            "status": "ok",
            "mock_pipeline": settings.mock_pipeline,
            "tts_backend": settings.tts_backend,
        }

    @app.post("/api/jobs", response_model=Job, status_code=status.HTTP_202_ACCEPTED)
    async def create_job(request: CreateJob) -> Job:
        if request.source_job_id:
            try:
                store.get(request.source_job_id)
            except KeyError as exc:
                raise HTTPException(status_code=404, detail="Source job not found") from exc
            if not store.chapters(request.source_job_id):
                raise HTTPException(status_code=409, detail="Source job has no saved chapters")
        if request.voice_id:
            try:
                voice = store.get_voice(request.voice_id)
            except KeyError as exc:
                raise HTTPException(status_code=404, detail="Voice not found") from exc
            if request.synthesis_mode != SynthesisMode.DESIGNED_CLONE:
                raise HTTPException(
                    status_code=400, detail="Reusable voices require design + clone"
                )
            if voice.status != VoiceStatus.READY:
                raise HTTPException(status_code=409, detail="Voice is not ready")
        job = store.create(request)
        workers.submit(job.id)
        return job

    @app.get("/api/jobs", response_model=list[Job])
    async def list_jobs() -> list[Job]:
        return store.list()

    @app.delete("/api/jobs", status_code=status.HTTP_200_OK)
    async def hide_all_jobs() -> dict[str, int]:
        return {"hidden": store.hide_all()}

    @app.post("/api/jobs/cancel-pending")
    async def cancel_pending_jobs() -> dict[str, int]:
        cancelled = 0
        for job in store.list(limit=10_000, include_hidden=True):
            if job.status == "queued":
                workers.cancel(job.id)
                store.update(job.id, status="cancelled", stage="Cancelled", error=None)
                cancelled += 1
        return {"cancelled": cancelled}

    @app.get("/api/jobs/{job_id}", response_model=Job)
    async def get_job(job_id: str) -> Job:
        try:
            return store.get(job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Job not found") from exc

    @app.delete("/api/jobs/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def hide_job(job_id: str) -> None:
        try:
            store.hide(job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Job not found") from exc

    @app.post("/api/jobs/{job_id}/cancel", response_model=Job)
    async def cancel_job(job_id: str) -> Job:
        try:
            job = store.get(job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Job not found") from exc
        if job.status not in {"queued", "crawling", "synthesizing"}:
            raise HTTPException(status_code=409, detail="Job is not active")
        workers.cancel(job.id)
        return store.update(job.id, status="cancelled", stage="Cancelling", error=None)

    @app.get("/api/jobs/{job_id}/chapters", response_model=list[ChapterRecord])
    async def get_chapters(
        job_id: str,
        offset: int | None = Query(default=None, ge=0),
        limit: int | None = Query(default=None, ge=1, le=200),
    ) -> list[ChapterRecord]:
        try:
            store.get(job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Job not found") from exc
        return store.chapters(job_id, offset=offset, limit=limit)

    @app.get("/api/jobs/{job_id}/chapters/{chapter_index}/audio")
    async def chapter_audio(job_id: str, chapter_index: int) -> StreamingResponse:
        records = {chapter.index: chapter for chapter in store.chapters(job_id)}
        chapter = records.get(chapter_index)
        if chapter is None or chapter.status != "completed":
            raise HTTPException(status_code=404, detail="Chapter audio not found")
        path = settings.data_dir / "jobs" / job_id / "audio" / f"chapter-{chapter_index:04d}.wav"
        if not path.is_file():
            raise HTTPException(status_code=404, detail="Chapter audio file is missing")
        return stream_file(path, "audio/wav", path.name)

    @app.get("/api/jobs/{job_id}/voice-preview")
    async def voice_preview(job_id: str) -> StreamingResponse:
        try:
            job = store.get(job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Job not found") from exc
        path = settings.data_dir / "jobs" / job.id / "voice-reference.wav"
        if not path.is_file():
            raise HTTPException(status_code=404, detail="Voice preview is not ready")
        return stream_file(path, "audio/wav", "voice-reference.wav")

    def archive_job(job_id: str) -> tuple[Job, list[Path]]:
        try:
            job = store.get(job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Job not found") from exc
        if job.status != "completed":
            raise HTTPException(status_code=409, detail="Audiobook is not complete")
        if not job.output_dir:
            raise HTTPException(status_code=404, detail="Generated files have been removed")
        files = [
            settings.data_dir
            / "jobs"
            / job.id
            / "audio"
            / f"chapter-{chapter.index:04d}.wav"
            for chapter in store.chapters(job.id)
        ]
        return job, files

    def archive_response(
        job_id: str, output_format: str, total_files: int
    ) -> ArchiveStatus:
        state = archives.status(job_id, output_format, total_files)
        return ArchiveStatus(
            **vars(state),
            format=output_format,
            download_url=(
                f"/api/jobs/{job_id}/download?format={output_format}"
                if state.state == "ready"
                else None
            ),
        )

    @app.get("/api/jobs/{job_id}/download/status", response_model=ArchiveStatus)
    async def download_status(
        job_id: str,
        output_format: Literal["mp3", "wav"] = Query(default="mp3", alias="format"),
    ) -> ArchiveStatus:
        _, files = archive_job(job_id)
        return archive_response(job_id, output_format, len(files))

    @app.post("/api/jobs/{job_id}/download/prepare", response_model=ArchiveStatus)
    async def prepare_download(
        job_id: str,
        output_format: Literal["mp3", "wav"] = Query(default="mp3", alias="format"),
    ) -> ArchiveStatus:
        _, files = archive_job(job_id)
        archives.prepare(job_id, output_format, files)
        return archive_response(job_id, output_format, len(files))

    @app.get("/api/jobs/{job_id}/download")
    async def download_job(
        job_id: str,
        output_format: Literal["mp3", "wav"] = Query(default="mp3", alias="format"),
    ) -> StreamingResponse:
        job, files = archive_job(job_id)
        state = archives.status(job.id, output_format, len(files))
        if state.state != "ready":
            raise HTTPException(status_code=409, detail="Audiobook ZIP is not ready")
        archive = archives.archive_path(job.id, output_format)
        return stream_file(
            archive, "application/zip", archive_filename(job.title, output_format)
        )

    @app.post("/api/voices", response_model=Voice, status_code=status.HTTP_202_ACCEPTED)
    async def create_voice(request: CreateVoice) -> Voice:
        voice = store.create_voice(request)
        workers.submit_voice(voice.id)
        return voice

    @app.get("/api/voices", response_model=list[Voice])
    async def list_voices() -> list[Voice]:
        return store.list_voices()

    @app.get("/api/voices/{voice_id}", response_model=Voice)
    async def get_voice(voice_id: str) -> Voice:
        try:
            return store.get_voice(voice_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Voice not found") from exc

    @app.get("/api/voices/{voice_id}/preview")
    async def reusable_voice_preview(voice_id: str) -> StreamingResponse:
        try:
            voice = store.get_voice(voice_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Voice not found") from exc
        path = settings.data_dir / "voices" / voice.id / "preview.wav"
        if voice.status != VoiceStatus.READY or not path.is_file():
            raise HTTPException(status_code=404, detail="Voice preview is not ready")
        return stream_file(path, "audio/wav", "voice-preview.wav")

    @app.get("/api/storage", response_model=list[StorageEntry])
    async def list_storage() -> list[StorageEntry]:
        entries: list[StorageEntry] = []
        for job in store.list(include_hidden=True):
            directory = settings.data_dir / "jobs" / job.id
            files = [path for path in directory.rglob("*") if path.is_file()]
            entries.append(
                StorageEntry(
                    job_id=job.id,
                    title=job.title or "Untitled audiobook",
                    status=job.status,
                    hidden=job.hidden,
                    file_count=len(files),
                    size_bytes=sum(path.stat().st_size for path in files),
                )
            )
        return entries

    @app.delete("/api/storage/jobs/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_job_files(job_id: str) -> None:
        try:
            job = store.get(job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Job not found") from exc
        if job.status in {"queued", "crawling", "synthesizing"}:
            raise HTTPException(status_code=409, detail="Cannot delete files for an active job")
        if archives.is_preparing(job.id):
            raise HTTPException(status_code=409, detail="Archive preparation is in progress")
        directory = settings.data_dir / "jobs" / job.id
        if directory.is_dir():
            shutil.rmtree(directory)
        store.clear_output_references(job.id)

    @app.delete("/api/storage", status_code=status.HTTP_200_OK)
    async def delete_all_job_files() -> dict[str, int]:
        deleted = 0
        skipped_active = 0
        for job in store.list(limit=10_000, include_hidden=True):
            if job.status in {"queued", "crawling", "synthesizing"}:
                skipped_active += 1
                continue
            if archives.is_preparing(job.id):
                skipped_active += 1
                continue
            directory = settings.data_dir / "jobs" / job.id
            if directory.is_dir():
                shutil.rmtree(directory)
                deleted += 1
            store.clear_output_references(job.id)
        return {"deleted": deleted, "skipped_active": skipped_active}

    return app


app = create_app()


def run() -> None:
    uvicorn.run("audiobook.main:app", host="127.0.0.1", port=8000)
