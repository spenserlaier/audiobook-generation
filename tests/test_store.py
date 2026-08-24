import sqlite3

from audiobook.models import Chapter, CreateJob, JobStatus, SynthesisMode
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
    assert reopened.get(job.id).synthesis_mode == SynthesisMode.DESIGNED_CLONE
    assert reopened.get(job.id).source_job_id is None


def test_recovery_cancels_interrupted_job(tmp_path):
    store = JobStore(tmp_path / "state.sqlite3")
    interrupted = store.create(CreateJob(novel_url="https://example.com/interrupted"))
    queued = store.create(CreateJob(novel_url="https://example.com/queued"))
    store.update(interrupted.id, status=JobStatus.CRAWLING)
    assert store.recover_interrupted() == [queued.id]
    assert store.get(interrupted.id).status == JobStatus.CANCELLED
    assert store.get(queued.id).status == JobStatus.QUEUED


def test_existing_database_gets_voice_design_columns(tmp_path):
    path = tmp_path / "old.sqlite3"
    with sqlite3.connect(path) as db:
        db.execute("""
            CREATE TABLE jobs (
                id TEXT PRIMARY KEY, novel_url TEXT NOT NULL, title TEXT,
                chapter_limit INTEGER, language TEXT NOT NULL, speaker TEXT NOT NULL,
                voice_instruction TEXT NOT NULL, status TEXT NOT NULL, stage TEXT NOT NULL,
                progress REAL NOT NULL, chapters_total INTEGER NOT NULL,
                chapters_completed INTEGER NOT NULL, error TEXT, output_dir TEXT,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            )
        """)
    store = JobStore(path)
    job = store.create(CreateJob(novel_url="https://example.com/new"))
    assert job.synthesis_mode == SynthesisMode.DESIGNED_CLONE
    assert job.voice_description


def test_chapters_can_be_paginated_and_jobs_bulk_hidden(tmp_path):
    store = JobStore(tmp_path / "state.sqlite3")
    jobs = [
        store.create(CreateJob(novel_url=f"https://example.com/book-{index}"))
        for index in range(2)
    ]
    store.replace_chapters(
        jobs[0].id,
        [Chapter(index=index, title=f"Chapter {index}", text="Text") for index in range(1, 121)],
    )

    page = store.chapters(jobs[0].id, offset=50, limit=50)
    assert len(page) == 50
    assert page[0].index == 51
    assert page[-1].index == 100
    assert store.hide_all() == 2
    assert store.list() == []
    assert len(store.list(include_hidden=True)) == 2
