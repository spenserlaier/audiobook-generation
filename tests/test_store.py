from audiobook.models import Chapter, CreateJob, JobStatus
from audiobook.store import JobStore


def test_job_and_chapter_state_persists(tmp_path):
    path = tmp_path / "state.sqlite3"
    store = JobStore(path)
    job = store.create(CreateJob(novel_url="https://example.com/book"))
    store.replace_chapters(job.id, [Chapter(index=1, title="One", text="Text")])
    store.update(job.id, status=JobStatus.SYNTHESIZING, chapters_total=1)
    store.update_chapter(job.id, 1, status="completed", audio_url="/audio")

    reopened = JobStore(path)
    assert reopened.get(job.id).status == JobStatus.SYNTHESIZING
    assert reopened.chapters(job.id)[0].audio_url == "/audio"


def test_recovery_requeues_active_job(tmp_path):
    store = JobStore(tmp_path / "state.sqlite3")
    job = store.create(CreateJob(novel_url="https://example.com/book"))
    store.update(job.id, status=JobStatus.CRAWLING)
    assert store.recover_interrupted() == [job.id]
    assert store.get(job.id).status == JobStatus.QUEUED
