import pytest
from pydantic import ValidationError

from audiobook.config import Settings


def test_real_gpu_pipeline_rejects_multiple_workers():
    with pytest.raises(ValidationError, match="WORKER_COUNT=1"):
        Settings(worker_count=2)


def test_mock_pipeline_allows_multiple_workers():
    settings = Settings(worker_count=2, mock_pipeline=True)

    assert settings.worker_count == 2


def test_generation_limit_cannot_exceed_static_cache():
    with pytest.raises(ValidationError, match="static cache length"):
        Settings(tts_max_seq_len=1024, tts_max_new_tokens=1025)
