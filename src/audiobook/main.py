from contextlib import asynccontextmanager
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import uvicorn
from fastapi import FastAPI, HTTPException, status
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .config import Settings
from .models import ChapterRecord, CreateJob, CreateVoice, Job, SynthesisMode, Voice, VoiceStatus
from .pipeline import Pipeline, WorkerPool
from .store import JobStore


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    settings.prepare()
    store = JobStore(settings.database_path)
    workers = WorkerPool(Pipeline(settings, store), settings.worker_count)

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

    static_dir = Path(__file__).parent / "static"
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

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

    @app.get("/", include_in_schema=False)
    async def index() -> FileResponse:
        return FileResponse(static_dir / "index.html")

    @app.get("/api/health")
    async def health() -> dict[str, str | bool]:
        return {
            "status": "ok",
            "mock_pipeline": settings.mock_pipeline,
            "tts_backend": settings.tts_backend,
        }

    @app.post("/api/jobs", response_model=Job, status_code=status.HTTP_202_ACCEPTED)
    async def create_job(request: CreateJob) -> Job:
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

    @app.get("/api/jobs/{job_id}", response_model=Job)
    async def get_job(job_id: str) -> Job:
        try:
            return store.get(job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Job not found") from exc

    @app.get("/api/jobs/{job_id}/chapters", response_model=list[ChapterRecord])
    async def get_chapters(job_id: str) -> list[ChapterRecord]:
        try:
            store.get(job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Job not found") from exc
        return store.chapters(job_id)

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

    @app.get("/api/jobs/{job_id}/download")
    async def download_job(job_id: str) -> StreamingResponse:
        try:
            job = store.get(job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Job not found") from exc
        if job.status != "completed":
            raise HTTPException(status_code=409, detail="Audiobook is not complete")
        archive = settings.data_dir / "jobs" / job.id / "audiobook.zip"
        chapters = store.chapters(job.id)
        with ZipFile(archive, "w", compression=ZIP_DEFLATED) as bundle:
            for chapter in chapters:
                path = (
                    settings.data_dir
                    / "jobs"
                    / job.id
                    / "audio"
                    / f"chapter-{chapter.index:04d}.wav"
                )
                if path.is_file():
                    bundle.write(path, arcname=path.name)
        return stream_file(archive, "application/zip", "audiobook.zip")

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

    return app


app = create_app()


def run() -> None:
    uvicorn.run("audiobook.main:app", host="127.0.0.1", port=8000)
