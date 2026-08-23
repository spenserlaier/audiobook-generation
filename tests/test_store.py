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


def test_recovery_requeues_active_job(tmp_path):
    store = JobStore(tmp_path / "state.sqlite3")
    job = store.create(CreateJob(novel_url="https://example.com/book"))
    store.update(job.id, status=JobStatus.CRAWLING)
    assert store.recover_interrupted() == [job.id]
    assert store.get(job.id).status == JobStatus.QUEUED


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
