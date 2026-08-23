from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    data_dir: Path = Path("data")
    crawler_command: str = "audiobook-lncrawl"
    tts_model: str = "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice"
    voice_design_model: str = "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign"
    voice_clone_model: str = "Qwen/Qwen3-TTS-12Hz-1.7B-Base"
    tts_backend: Literal["official", "faster"] = "faster"
    tts_device: str = "cuda:0"
    tts_dtype: str = "bfloat16"
    tts_attention: str = "auto"
    tts_max_seq_len: int = Field(default=2048, ge=256)
    tts_max_new_tokens: int = Field(default=2048, ge=1)
    chunk_chars: int = Field(default=1200, ge=1)
    mock_pipeline: bool = False
    worker_count: int = Field(default=1, ge=1)
    tts_release_after_job: bool = True

    model_config = SettingsConfigDict(env_prefix="AUDIOBOOK_", env_file=".env")

    @model_validator(mode="after")
    def validate_gpu_safety(self) -> "Settings":
        if not self.mock_pipeline and self.worker_count != 1:
            raise ValueError("GPU synthesis requires AUDIOBOOK_WORKER_COUNT=1")
        if self.tts_max_new_tokens > self.tts_max_seq_len:
            raise ValueError("TTS max new tokens cannot exceed the static cache length")
        return self

    @property
    def database_path(self) -> Path:
        return self.data_dir / "audiobooks.sqlite3"

    def prepare(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
