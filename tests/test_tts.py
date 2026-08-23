from audiobook.audio import write_mock_wav
from audiobook.config import Settings
from audiobook.tts import QwenSynthesizer, resolve_attention


def test_attention_automatically_uses_sdpa_without_flash_attention():
    assert resolve_attention("auto", flash_available=False) == "sdpa"


def test_attention_automatically_prefers_installed_flash_attention():
    assert resolve_attention("auto", flash_available=True) == "flash_attention_2"


def test_explicit_attention_configuration_is_preserved():
    assert resolve_attention("eager", flash_available=False) == "eager"
    assert resolve_attention("", flash_available=False) is None


def test_clone_synthesis_creates_missing_output_directory(monkeypatch, tmp_path):
    class FakeModel:
        def generate_voice_clone(self, **kwargs):
            return [[0.0]], 16_000

    class FakeSoundFile:
        @staticmethod
        def write(path, wav, sample_rate):
            assert path.parent.is_dir()
            write_mock_wav(path, "audio", sample_rate)

    synthesizer = QwenSynthesizer(Settings(data_dir=tmp_path))
    monkeypatch.setattr(synthesizer, "_dependencies", lambda: (None, FakeSoundFile, None))
    monkeypatch.setattr(synthesizer, "_load", lambda _: FakeModel())
    output = tmp_path / "new" / "nested" / "chapter.wav"

    synthesizer.synthesize_clone("Chapter text", output, "English", object())

    assert output.is_file()
