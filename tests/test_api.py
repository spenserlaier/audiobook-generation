import asyncio
import time

import httpx
import pytest

from audiobook.config import Settings
from audiobook.main import create_app


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_mock_job_completes_and_serves_audio(tmp_path):
    app = create_app(Settings(data_dir=tmp_path, mock_pipeline=True))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/jobs",
                json={"novel_url": "https://example.com/novel", "chapter_limit": 2},
            )
            assert response.status_code == 202
            job_id = response.json()["id"]
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                job = (await client.get(f"/api/jobs/{job_id}")).json()
                if job["status"] in {"completed", "failed"}:
                    break
                await asyncio.sleep(0.02)
            assert job["status"] == "completed", job
            assert job["chapters_completed"] == 2

            chapters = (await client.get(f"/api/jobs/{job_id}/chapters")).json()
            assert len(chapters) == 2
            assert chapters[0]["audio_url"].endswith("/chapters/1/audio")
            audio_path = tmp_path / "jobs" / job_id / "audio" / "chapter-0001.wav"
            assert audio_path.read_bytes().startswith(b"RIFF")


@pytest.mark.anyio
async def test_invalid_url_and_missing_job(tmp_path):
    app = create_app(Settings(data_dir=tmp_path, mock_pipeline=True))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post("/api/jobs", json={"novel_url": "not a URL"})
            assert response.status_code == 422
            assert (await client.get("/api/jobs/missing")).status_code == 404
