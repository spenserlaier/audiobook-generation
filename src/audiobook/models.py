from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field, HttpUrl


class JobStatus(StrEnum):
    QUEUED = "queued"
    CRAWLING = "crawling"
    SYNTHESIZING = "synthesizing"
    COMPLETED = "completed"
    FAILED = "failed"


class CreateJob(BaseModel):
    novel_url: HttpUrl
    title: str | None = Field(default=None, max_length=300)
    chapter_limit: int | None = Field(default=None, ge=1, le=10_000)
    language: str = Field(default="Auto", max_length=40)
    speaker: str = Field(default="Ryan", max_length=80)
    voice_instruction: str = Field(default="", max_length=500)


class Chapter(BaseModel):
    index: int
    title: str
    text: str


class ChapterRecord(Chapter):
    job_id: str
    status: str
    audio_url: str | None = None
    error: str | None = None


class Job(BaseModel):
    id: str
    novel_url: str
    title: str | None
    chapter_limit: int | None
    language: str
    speaker: str
    voice_instruction: str
    status: JobStatus
    stage: str
    progress: float
    chapters_total: int
    chapters_completed: int
    error: str | None
    output_dir: str | None
    created_at: datetime
    updated_at: datetime
