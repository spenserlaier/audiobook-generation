from __future__ import annotations

import sqlite3
import uuid
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

from .models import (
    Chapter,
    ChapterRecord,
    CreateJob,
    CreateVoice,
    Job,
    JobStatus,
    Voice,
    VoiceStatus,
)


class JobStore:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY, novel_url TEXT NOT NULL, title TEXT,
                    chapter_limit INTEGER, language TEXT NOT NULL, speaker TEXT NOT NULL,
                    voice_instruction TEXT NOT NULL, status TEXT NOT NULL, stage TEXT NOT NULL,
                    progress REAL NOT NULL DEFAULT 0, chapters_total INTEGER NOT NULL DEFAULT 0,
                    chapters_completed INTEGER NOT NULL DEFAULT 0, error TEXT, output_dir TEXT,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                )
            """)
            columns = {row["name"] for row in db.execute("PRAGMA table_info(jobs)")}
            migrations = {
                "synthesis_mode": "TEXT NOT NULL DEFAULT 'designed_clone'",
                "voice_description": "TEXT NOT NULL DEFAULT ''",
                "reference_text": "TEXT NOT NULL DEFAULT ''",
                "voice_preview_url": "TEXT",
                "voice_id": "TEXT",
                "hidden": "INTEGER NOT NULL DEFAULT 0",
            }
            for name, definition in migrations.items():
                if name not in columns:
                    db.execute(f"ALTER TABLE jobs ADD COLUMN {name} {definition}")
            db.execute("""
                CREATE TABLE IF NOT EXISTS chapters (
                    job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
                    chapter_index INTEGER NOT NULL, title TEXT NOT NULL, text TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'queued', audio_url TEXT, error TEXT,
                    PRIMARY KEY (job_id, chapter_index)
                )
            """)
            db.execute("""
                CREATE TABLE IF NOT EXISTS voices (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL, language TEXT NOT NULL,
                    description TEXT NOT NULL, reference_text TEXT NOT NULL,
                    status TEXT NOT NULL, preview_url TEXT, error TEXT,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                )
            """)

    def create(self, request: CreateJob) -> Job:
        now = datetime.now(UTC).isoformat()
        job_id = uuid.uuid4().hex
        with self._connect() as db:
            db.execute(
                """INSERT INTO jobs (
                       id, novel_url, title, chapter_limit, language, speaker,
                       voice_instruction, status, stage, progress, chapters_total,
                       chapters_completed, error, output_dir, created_at, updated_at,
                       synthesis_mode, voice_description, reference_text,
                       voice_preview_url, voice_id
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    job_id,
                    str(request.novel_url),
                    request.title,
                    request.chapter_limit,
                    request.language,
                    request.speaker,
                    request.voice_instruction,
                    JobStatus.QUEUED,
                    "Waiting for worker",
                    0,
                    0,
                    0,
                    None,
                    None,
                    now,
                    now,
                    request.synthesis_mode,
                    request.voice_description,
                    request.reference_text,
                    None,
                    request.voice_id,
                ),
            )
        return self.get(job_id)

    def create_voice(self, request: CreateVoice) -> Voice:
        now = datetime.now(UTC).isoformat()
        voice_id = uuid.uuid4().hex
        with self._connect() as db:
            db.execute(
                """INSERT INTO voices (id, name, language, description, reference_text,
                   status, preview_url, error, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (voice_id, request.name, request.language, request.description,
                 request.reference_text, VoiceStatus.QUEUED, None, None, now, now),
            )
        return self.get_voice(voice_id)

    def get_voice(self, voice_id: str) -> Voice:
        with self._connect() as db:
            row = db.execute("SELECT * FROM voices WHERE id = ?", (voice_id,)).fetchone()
        if row is None:
            raise KeyError(voice_id)
        return Voice.model_validate(dict(row))

    def list_voices(self, limit: int = 100) -> list[Voice]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT * FROM voices ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [Voice.model_validate(dict(row)) for row in rows]

    def update_voice(self, voice_id: str, **values: object) -> Voice:
        allowed = set(Voice.model_fields) - {"id", "created_at", "updated_at"}
        values = {key: value for key, value in values.items() if key in allowed}
        values["updated_at"] = datetime.now(UTC).isoformat()
        assignments = ", ".join(f"{key} = ?" for key in values)
        normalized = [v.value if isinstance(v, StrEnum) else v for v in values.values()]
        with self._connect() as db:
            db.execute(f"UPDATE voices SET {assignments} WHERE id = ?", (*normalized, voice_id))
        return self.get_voice(voice_id)

    def get(self, job_id: str) -> Job:
        with self._connect() as db:
            row = db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            raise KeyError(job_id)
        return Job.model_validate(dict(row))

    def list(self, limit: int = 100, include_hidden: bool = False) -> list[Job]:
        with self._connect() as db:
            if include_hidden:
                rows = db.execute(
                    "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)
                ).fetchall()
            else:
                rows = db.execute(
                    "SELECT * FROM jobs WHERE hidden = 0 ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        return [Job.model_validate(dict(row)) for row in rows]

    def hide(self, job_id: str) -> Job:
        return self.update(job_id, hidden=True)

    def clear_output_references(self, job_id: str) -> None:
        with self._connect() as db:
            db.execute(
                "UPDATE jobs SET output_dir = NULL, voice_preview_url = NULL WHERE id = ?",
                (job_id,),
            )
            db.execute(
                "UPDATE chapters SET audio_url = NULL WHERE job_id = ?", (job_id,)
            )

    def update(self, job_id: str, **values: object) -> Job:
        allowed = set(Job.model_fields) - {"id", "created_at", "updated_at"}
        values = {key: value for key, value in values.items() if key in allowed}
        values["updated_at"] = datetime.now(UTC).isoformat()
        assignments = ", ".join(f"{key} = ?" for key in values)
        normalized = [
            value.value if isinstance(value, StrEnum) else value for value in values.values()
        ]
        with self._connect() as db:
            db.execute(f"UPDATE jobs SET {assignments} WHERE id = ?", (*normalized, job_id))
        return self.get(job_id)

    def replace_chapters(self, job_id: str, chapters: list[Chapter]) -> None:
        with self._connect() as db:
            db.execute("DELETE FROM chapters WHERE job_id = ?", (job_id,))
            db.executemany(
                """INSERT INTO chapters
                   (job_id, chapter_index, title, text, status) VALUES (?, ?, ?, ?, 'queued')""",
                [(job_id, c.index, c.title, c.text) for c in chapters],
            )

    def chapters(self, job_id: str) -> list[ChapterRecord]:
        with self._connect() as db:
            rows = db.execute(
                """SELECT job_id, chapter_index AS 'index', title, text, status,
                          audio_url, error FROM chapters WHERE job_id = ?
                   ORDER BY chapter_index""",
                (job_id,),
            ).fetchall()
        return [ChapterRecord.model_validate(dict(row)) for row in rows]

    def update_chapter(self, job_id: str, index: int, **values: object) -> None:
        allowed = {"status", "audio_url", "error"}
        values = {key: value for key, value in values.items() if key in allowed}
        if not values:
            return
        assignments = ", ".join(f"{key} = ?" for key in values)
        with self._connect() as db:
            db.execute(
                f"UPDATE chapters SET {assignments} WHERE job_id = ? AND chapter_index = ?",
                (*values.values(), job_id, index),
            )

    def recover_interrupted(self) -> list[str]:
        active = (JobStatus.QUEUED, JobStatus.CRAWLING, JobStatus.SYNTHESIZING)
        with self._connect() as db:
            rows = db.execute("SELECT id FROM jobs WHERE status IN (?, ?, ?)", active).fetchall()
            db.execute(
                "UPDATE jobs SET status = ?, stage = ? WHERE status IN (?, ?)",
                (
                    JobStatus.QUEUED,
                    "Resuming after restart",
                    JobStatus.CRAWLING,
                    JobStatus.SYNTHESIZING,
                ),
            )
        return [row["id"] for row in rows]

    def recover_interrupted_voices(self) -> list[str]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT id FROM voices WHERE status IN (?, ?)",
                (VoiceStatus.QUEUED, VoiceStatus.GENERATING),
            ).fetchall()
            db.execute(
                "UPDATE voices SET status = ? WHERE status = ?",
                (VoiceStatus.QUEUED, VoiceStatus.GENERATING),
            )
        return [row["id"] for row in rows]
