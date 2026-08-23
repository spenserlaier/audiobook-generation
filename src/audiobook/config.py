from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    data_dir: Path = Path("data")
    crawler_command: str = "lncrawl"
    tts_model: str = "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice"
    voice_design_model: str = "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign"
    voice_clone_model: str = "Qwen/Qwen3-TTS-12Hz-1.7B-Base"
    tts_device: str = "cuda:0"
    tts_dtype: str = "bfloat16"
    tts_attention: str = "flash_attention_2"
    chunk_chars: int = 1200
    mock_pipeline: bool = False
    worker_count: int = 1

    model_config = SettingsConfigDict(env_prefix="AUDIOBOOK_", env_file=".env")

    @property
    def database_path(self) -> Path:
        return self.data_dir / "audiobooks.sqlite3"

    def prepare(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
