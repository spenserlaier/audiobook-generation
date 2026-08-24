import json

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
    assert output.with_suffix(".quality.json").is_file()


def test_clone_synthesis_retries_runaway_duration_with_safer_sampling(
    monkeypatch, tmp_path
):
    calls = []

    class FakeModel:
        def generate_voice_clone(self, **kwargs):
            calls.append(kwargs)
            length = 300 if len(calls) == 1 else 100
            return [[0.0] * length], 10

    class FakeSoundFile:
        @staticmethod
        def write(path, wav, sample_rate):
            write_mock_wav(path, "audio", sample_rate)

    settings = Settings(data_dir=tmp_path, tts_quality_retries=2)
    synthesizer = QwenSynthesizer(settings)
    monkeypatch.setattr(synthesizer, "_dependencies", lambda: (None, FakeSoundFile, None))
    monkeypatch.setattr(synthesizer, "_load", lambda _: FakeModel())
    output = tmp_path / "chapter.wav"

    synthesizer.synthesize_clone("A short sentence.", output, "English", object())

    assert len(calls) == 2
    assert calls[0]["temperature"] == 0.75
    assert calls[1]["temperature"] == 0.7
    assert calls[0]["repetition_penalty"] == 1.08
    assert calls[1]["repetition_penalty"] == 1.1
    manifest = json.loads(output.with_suffix(".quality.json").read_text())
    assert manifest["chunks"][0]["attempts"][0]["rejected_as_runaway"] is True
    assert manifest["chunks"][0]["attempts"][1]["rejected_as_runaway"] is False


def test_faster_backend_uses_cuda_graph_compatible_load_options(monkeypatch, tmp_path):
    class FakeCuda:
        @staticmethod
        def is_available():
            return True

    class FakeTorch:
        bfloat16 = object()
        cuda = FakeCuda()

    class FakeModelClass:
        called_with = None

        @classmethod
        def from_pretrained(cls, model_id, **kwargs):
            cls.called_with = (model_id, kwargs)
            return object()

    settings = Settings(
        data_dir=tmp_path,
        tts_backend="faster",
        tts_max_seq_len=1024,
        tts_max_new_tokens=1024,
    )
    synthesizer = QwenSynthesizer(settings)
    monkeypatch.setattr(
        synthesizer, "_dependencies", lambda: (FakeTorch, object(), FakeModelClass)
    )

    synthesizer._load(settings.voice_clone_model)

    model_id, kwargs = FakeModelClass.called_with
    assert model_id == settings.voice_clone_model
    assert kwargs["device"] == "cuda:0"
    assert kwargs["attn_implementation"] == "sdpa"
    assert kwargs["max_seq_len"] == 1024
    assert "device_map" not in kwargs


def test_faster_backend_builds_prompt_with_wrapped_upstream_model(monkeypatch, tmp_path):
    expected = object()

    class PromptModel:
        def create_voice_clone_prompt(self, **kwargs):
            assert kwargs["x_vector_only_mode"] is False
            return expected

    class FasterModel:
        model = PromptModel()

    synthesizer = QwenSynthesizer(Settings(data_dir=tmp_path, tts_backend="faster"))
    monkeypatch.setattr(synthesizer, "_load", lambda _: FasterModel())

    prompt = synthesizer.create_clone_prompt(tmp_path / "reference.wav", "reference")

    assert prompt is expected
