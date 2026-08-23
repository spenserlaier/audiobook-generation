import asyncio
import time
from io import BytesIO
from zipfile import ZipFile

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
            assert job["synthesis_mode"] == "designed_clone"
            assert job["voice_preview_url"].endswith("/voice-preview")
            reference = tmp_path / "jobs" / job_id / "voice-reference.wav"
            assert reference.read_bytes().startswith(b"RIFF")

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


@pytest.mark.anyio
async def test_reusable_voice_preview_and_job_download(tmp_path):
    app = create_app(Settings(data_dir=tmp_path, mock_pipeline=True))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/voices", json={"name": "Night narrator"}
            )
            assert response.status_code == 202
            voice_id = response.json()["id"]
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                voice = (await client.get(f"/api/voices/{voice_id}")).json()
                if voice["status"] in {"ready", "failed"}:
                    break
                await asyncio.sleep(0.02)
            assert voice["status"] == "ready", voice
            assert (await client.get(voice["preview_url"])).content.startswith(b"RIFF")

            response = await client.post(
                "/api/jobs",
                json={
                    "novel_url": "https://example.com/novel",
                    "chapter_limit": 2,
                    "voice_id": voice_id,
                },
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
            assert job["voice_preview_url"] == voice["preview_url"]
            archive = await client.get(f"/api/jobs/{job_id}/download")
            assert archive.status_code == 200
            with ZipFile(BytesIO(archive.content)) as bundle:
                assert bundle.namelist() == ["chapter-0001.wav", "chapter-0002.wav"]

            storage = (await client.get("/api/storage")).json()
            entry = next(item for item in storage if item["job_id"] == job_id)
            assert entry["file_count"] >= 3
            assert entry["size_bytes"] > 0
            page = (
                await client.get(f"/api/jobs/{job_id}/chapters?offset=1&limit=1")
            ).json()
            assert [chapter["index"] for chapter in page] == [2]

            response = await client.delete("/api/jobs")
            assert response.status_code == 200
            assert response.json()["hidden"] == 1
            assert all(item["id"] != job_id for item in (await client.get("/api/jobs")).json())
            storage = (await client.get("/api/storage")).json()
            assert next(item for item in storage if item["job_id"] == job_id)["hidden"] is True

            response = await client.delete("/api/storage")
            assert response.status_code == 200
            assert response.json() == {"deleted": 1, "skipped_active": 0}
            assert not (tmp_path / "jobs" / job_id).exists()
            assert (await client.get(f"/api/jobs/{job_id}")).json()["output_dir"] is None
            chapters = (await client.get(f"/api/jobs/{job_id}/chapters")).json()
            assert all(chapter["audio_url"] is None for chapter in chapters)
