from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import Settings
from .models import ChapterRecord, CreateJob, Job
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
        yield
        workers.stop()

    app = FastAPI(title="Audiobook Generator", version="0.1.0", lifespan=lifespan)
    app.state.store = store
    app.state.workers = workers

    static_dir = Path(__file__).parent / "static"
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

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
    async def chapter_audio(job_id: str, chapter_index: int) -> FileResponse:
        records = {chapter.index: chapter for chapter in store.chapters(job_id)}
        chapter = records.get(chapter_index)
        if chapter is None or chapter.status != "completed":
            raise HTTPException(status_code=404, detail="Chapter audio not found")
        path = settings.data_dir / "jobs" / job_id / "audio" / f"chapter-{chapter_index:04d}.wav"
        if not path.is_file():
            raise HTTPException(status_code=404, detail="Chapter audio file is missing")
        return FileResponse(path, media_type="audio/wav", filename=path.name)

    @app.get("/api/jobs/{job_id}/voice-preview")
    async def voice_preview(job_id: str) -> FileResponse:
        try:
            job = store.get(job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Job not found") from exc
        path = settings.data_dir / "jobs" / job.id / "voice-reference.wav"
        if not path.is_file():
            raise HTTPException(status_code=404, detail="Voice preview is not ready")
        return FileResponse(path, media_type="audio/wav", filename="voice-reference.wav")

    return app


app = create_app()


def run() -> None:
    uvicorn.run("audiobook.main:app", host="127.0.0.1", port=8000)
