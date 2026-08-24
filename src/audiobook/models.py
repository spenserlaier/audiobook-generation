from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field, HttpUrl


class JobStatus(StrEnum):
    QUEUED = "queued"
    CRAWLING = "crawling"
    SYNTHESIZING = "synthesizing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SynthesisMode(StrEnum):
    DESIGNED_CLONE = "designed_clone"
    CUSTOM_VOICE = "custom_voice"


class CreateJob(BaseModel):
    novel_url: HttpUrl
    title: str | None = Field(default=None, max_length=300)
    chapter_limit: int | None = Field(default=None, ge=1, le=10_000)
    language: str = Field(default="Auto", max_length=40)
    speaker: str = Field(default="Ryan", max_length=80)
    voice_instruction: str = Field(default="", max_length=500)
    synthesis_mode: SynthesisMode = SynthesisMode.DESIGNED_CLONE
    voice_id: str | None = Field(default=None, max_length=32)
    source_job_id: str | None = Field(default=None, max_length=32)
    voice_description: str = Field(
        default=(
            "A compelling, warm audiobook narrator with a clear mid-low register, measured "
            "pacing, subtle emotional range, crisp diction, and an intimate storytelling tone."
        ),
        min_length=1,
        max_length=1000,
    )
    reference_text: str = Field(
        default=(
            "The road disappeared into the evening mist, and with every quiet step, the old "
            "world fell farther behind. Ahead waited a story no one had dared to tell."
        ),
        min_length=1,
        max_length=1000,
    )


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
    synthesis_mode: SynthesisMode
    voice_id: str | None
    source_job_id: str | None
    voice_description: str
    reference_text: str
    voice_preview_url: str | None
    status: JobStatus
    stage: str
    progress: float
    chapters_total: int
    chapters_completed: int
    error: str | None
    output_dir: str | None
    created_at: datetime
    updated_at: datetime
    hidden: bool = False


class StorageEntry(BaseModel):
    job_id: str
    title: str
    status: JobStatus
    hidden: bool
    file_count: int
    size_bytes: int


class ArchiveStatus(BaseModel):
    format: str
    state: str
    completed_files: int
    total_files: int
    size_bytes: int
    error: str | None = None
    download_url: str | None = None


class VoiceStatus(StrEnum):
    QUEUED = "queued"
    GENERATING = "generating"
    READY = "ready"
    FAILED = "failed"


class CreateVoice(BaseModel):
    name: str = Field(default="Narrator", min_length=1, max_length=120)
    language: str = Field(default="Auto", max_length=40)
    description: str = Field(
        default=(
            "A compelling, warm audiobook narrator with a clear mid-low register, measured "
            "pacing, subtle emotional range, crisp diction, and an intimate storytelling tone."
        ),
        min_length=1,
        max_length=1000,
    )
    reference_text: str = Field(
        default=(
            "The road disappeared into the evening mist, and with every quiet step, the old "
            "world fell farther behind. Ahead waited a story no one had dared to tell."
        ),
        min_length=1,
        max_length=1000,
    )


class RenameVoice(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class Voice(BaseModel):
    id: str
    name: str
    language: str
    description: str
    reference_text: str
    status: VoiceStatus
    preview_url: str | None
    error: str | None
    created_at: datetime
    updated_at: datetime
