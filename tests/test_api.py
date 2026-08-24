import asyncio
import threading
import time
from io import BytesIO
from pathlib import Path
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
async def test_failed_voice_can_be_renamed_and_deleted_with_its_files(tmp_path):
    app = create_app(Settings(data_dir=tmp_path, mock_pipeline=True))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        created = (await client.post("/api/voices", json={"name": "Failed voice"})).json()
        voice_id = created["id"]
        app.state.store.update_voice(voice_id, status="failed", error="generation failed")
        voice_dir = tmp_path / "voices" / voice_id
        voice_dir.mkdir(parents=True)
        (voice_dir / "preview.wav").write_bytes(b"partial")

        renamed = await client.patch(
            f"/api/voices/{voice_id}", json={"name": "Archived attempt"}
        )
        assert renamed.status_code == 200
        assert renamed.json()["name"] == "Archived attempt"

        deleted = await client.delete(f"/api/voices/{voice_id}")
        assert deleted.status_code == 204
        assert not voice_dir.exists()
        assert (await client.get(f"/api/voices/{voice_id}")).status_code == 404


@pytest.mark.anyio
async def test_voice_used_by_active_job_cannot_be_deleted(tmp_path):
    app = create_app(Settings(data_dir=tmp_path, mock_pipeline=True))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        voice = (await client.post("/api/voices", json={"name": "In use"})).json()
        app.state.store.update_voice(voice["id"], status="ready", preview_url="/preview")
        job = await client.post(
            "/api/jobs",
            json={"novel_url": "https://example.com/book", "voice_id": voice["id"]},
        )
        assert job.status_code == 202

        response = await client.delete(f"/api/voices/{voice['id']}")

        assert response.status_code == 409
        assert response.json()["detail"] == "Cannot delete a voice used by an active job"


@pytest.mark.anyio
async def test_queued_jobs_can_be_cancelled(tmp_path):
    app = create_app(Settings(data_dir=tmp_path, mock_pipeline=True))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        first = (
            await client.post("/api/jobs", json={"novel_url": "https://example.com/one"})
        ).json()
        second = (
            await client.post("/api/jobs", json={"novel_url": "https://example.com/two"})
        ).json()
        response = await client.post(f"/api/jobs/{first['id']}/cancel")
        assert response.status_code == 200
        assert response.json()["status"] == "cancelled"
        response = await client.post("/api/jobs/cancel-pending")
        assert response.json() == {"cancelled": 1}
        assert (await client.get(f"/api/jobs/{second['id']}")).json()["status"] == "cancelled"


@pytest.mark.anyio
async def test_job_can_regenerate_from_saved_chapters(tmp_path):
    app = create_app(Settings(data_dir=tmp_path, mock_pipeline=True))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            source = (
                await client.post(
                    "/api/jobs",
                    json={"novel_url": "https://example.com/source", "chapter_limit": 3},
                )
            ).json()
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                source = (await client.get(f"/api/jobs/{source['id']}")).json()
                if source["status"] in {"completed", "failed"}:
                    break
                await asyncio.sleep(0.02)
            assert source["status"] == "completed", source

            regenerated = (
                await client.post(
                    "/api/jobs",
                    json={
                        "novel_url": source["novel_url"],
                        "title": "New performance",
                        "chapter_limit": 2,
                        "source_job_id": source["id"],
                        "synthesis_mode": "custom_voice",
                        "speaker": "Aiden",
                    },
                )
            ).json()
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                regenerated = (
                    await client.get(f"/api/jobs/{regenerated['id']}")
                ).json()
                if regenerated["status"] in {"completed", "failed"}:
                    break
                await asyncio.sleep(0.02)
            assert regenerated["status"] == "completed", regenerated
            assert regenerated["source_job_id"] == source["id"]
            assert regenerated["title"] == "New performance"
            assert regenerated["chapters_total"] == 2
            chapters = (
                await client.get(f"/api/jobs/{regenerated['id']}/chapters")
            ).json()
            assert [chapter["title"] for chapter in chapters] == ["Chapter 1", "Chapter 2"]


@pytest.mark.anyio
async def test_reusable_voice_preview_and_job_download(tmp_path, monkeypatch):
    conversion_lock = threading.Lock()
    active_conversions = 0
    max_active_conversions = 0

    def fake_ffmpeg(args, **_kwargs):
        nonlocal active_conversions, max_active_conversions
        with conversion_lock:
            active_conversions += 1
            max_active_conversions = max(max_active_conversions, active_conversions)
        time.sleep(0.05)
        source = Path(args[args.index("-i") + 1])
        Path(args[-1]).write_bytes(source.read_bytes())
        with conversion_lock:
            active_conversions -= 1
        assert args[args.index("-threads") + 1] == "1"

    monkeypatch.setattr("audiobook.archive.subprocess.run", fake_ffmpeg)
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
                    "title": "Night's Café: A Story!",
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
            status_response = await client.get(f"/api/jobs/{job_id}/download/status")
            assert status_response.json()["state"] == "idle"
            assert status_response.json()["format"] == "mp3"
            assert (await client.get(f"/api/jobs/{job_id}/download")).status_code == 409
            response = await client.post(f"/api/jobs/{job_id}/download/prepare")
            assert response.status_code == 200
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                archive_status = (
                    await client.get(f"/api/jobs/{job_id}/download/status")
                ).json()
                if archive_status["state"] in {"ready", "failed"}:
                    break
                await asyncio.sleep(0.02)
            assert archive_status["state"] == "ready", archive_status
            assert max_active_conversions == 2
            assert archive_status["completed_files"] == 2
            assert archive_status["download_url"].endswith("/download?format=mp3")
            archive = await client.get(archive_status["download_url"])
            assert archive.status_code == 200
            assert (
                archive.headers["content-disposition"]
                == 'attachment; filename="night-s-cafe-a-story-mp3.zip"'
            )
            with ZipFile(BytesIO(archive.content)) as bundle:
                assert bundle.namelist() == ["chapter-0001.mp3", "chapter-0002.mp3"]
            completed_size = archive_status["size_bytes"]
            response = await client.post(f"/api/jobs/{job_id}/download/prepare")
            assert response.json()["state"] == "ready"
            assert response.json()["size_bytes"] == completed_size
            assert not (
                tmp_path / "jobs" / job_id / ".audiobook-mp3.zip.part"
            ).exists()

            response = await client.post(
                f"/api/jobs/{job_id}/download/prepare?format=wav"
            )
            assert response.json()["format"] == "wav"
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                wav_status = (
                    await client.get(f"/api/jobs/{job_id}/download/status?format=wav")
                ).json()
                if wav_status["state"] in {"ready", "failed"}:
                    break
                await asyncio.sleep(0.02)
            assert wav_status["state"] == "ready", wav_status
            wav_archive = await client.get(wav_status["download_url"])
            assert wav_archive.headers["content-disposition"].endswith(
                'filename="night-s-cafe-a-story-wav.zip"'
            )
            with ZipFile(BytesIO(wav_archive.content)) as bundle:
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
