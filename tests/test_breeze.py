import json
import sys
import wave

import httpx

from audiobook.audio import write_mock_wav
from audiobook.breeze import BreezeSynthesizer
from audiobook.config import Settings
from audiobook.models import Chapter, CreateJob, JobStatus, TTSProvider
from audiobook.pipeline import Pipeline
from audiobook.store import JobStore


def test_breeze_design_and_clone_use_official_pcm_api(monkeypatch, tmp_path):
    calls = []

    def handle(request):
        body = request.read()
        calls.append(body)
        assert request.url.path == "/v1/audio/speech"
        return httpx.Response(
            200,
            headers={"x-sample-rate": "24000", "x-sample-format": "s16le"},
            content=b"\x00\x00" * 2400,
        )

    original_client = httpx.Client
    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kwargs: original_client(transport=httpx.MockTransport(handle), **kwargs),
    )
    synthesizer = BreezeSynthesizer(Settings(data_dir=tmp_path, breeze_chunk_chars=20))
    preview = tmp_path / "preview.wav"
    synthesizer.design_voice("A short preview.", "Warm narrator", "English", preview)
    prompt = synthesizer.create_clone_prompt(preview, "A short preview.")
    output = tmp_path / "chapters" / "chapter.wav"
    synthesizer.synthesize_clone(
        "First sentence. Second sentence.", output, "English", prompt, "Speak slowly"
    )

    with wave.open(str(output)) as audio:
        assert audio.getframerate() == 24000
        assert audio.getnchannels() == 1
        assert audio.getnframes() == 4800
    assert b"instruction=Warm+narrator" in calls[0]
    assert b"A short preview." in calls[1]
    assert b"Speak slowly" in calls[1]
    assert b'filename="preview.wav"' in calls[1]
    manifest = json.loads(output.with_suffix(".quality.json").read_text())
    assert len(manifest["chunks"]) == 2
    assert manifest["chunks"][0]["attempts"][0]["seed"] == 142


def test_breeze_rejects_incomplete_pcm(monkeypatch, tmp_path):
    synthesizer = BreezeSynthesizer(Settings(data_dir=tmp_path))

    class Response:
        status_code = 200
        headers = {"x-sample-rate": "24000", "x-sample-format": "s16le"}

        def iter_bytes(self):
            yield b"\x00"

    try:
        synthesizer._read_pcm(Response())
    except RuntimeError as exc:
        assert "incomplete PCM" in str(exc)
    else:
        raise AssertionError("Incomplete audio was accepted")


def test_pipeline_routes_breeze_job_and_voice_direction(tmp_path):
    settings = Settings(data_dir=tmp_path)
    store = JobStore(settings.database_path)
    source = store.create(CreateJob(novel_url="https://example.com/source"))
    store.replace_chapters(source.id, [Chapter(index=1, title="One", text="Chapter text")])
    job = store.create(
        CreateJob(
            novel_url="https://example.com/book",
            source_job_id=source.id,
            tts_provider=TTSProvider.BREEZE,
            voice_instruction="Speak slowly",
        )
    )
    calls = []

    class FakeBreeze:
        def design_voice(self, text, description, language, output):
            calls.append("design")
            write_mock_wav(output, text)

        def create_clone_prompt(self, audio, text):
            calls.append("prompt")
            return audio, text

        def synthesize_clone(self, text, output, language, prompt, instruction):
            calls.append(instruction)
            assert prompt[0].is_file()
            write_mock_wav(output, text)

        def release(self):
            calls.append("release")

    pipeline = Pipeline(settings, store)
    pipeline.breeze = FakeBreeze()
    pipeline.run(job.id)

    assert store.get(job.id).status == JobStatus.COMPLETED
    assert calls == ["design", "prompt", "Speak slowly", "release"]


def test_local_server_uses_venv_python_even_when_it_is_a_symlink(monkeypatch, tmp_path):
    runtime = tmp_path / "breeze-runtime"
    python = runtime / ".venv" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.symlink_to(sys.executable)
    source = runtime / "source" / "breeze_infer"
    source.mkdir(parents=True)
    (source / "api.py").write_text("")
    checkpoint = runtime / "checkpoint"
    checkpoint.mkdir()
    (checkpoint / "model.safetensors.index.json").write_text("{}")
    command = []

    class Process:
        def poll(self):
            return None

    def start(args, **kwargs):
        command.extend(args)
        return Process()

    monkeypatch.setattr("audiobook.breeze.subprocess.Popen", start)
    monkeypatch.setattr(
        httpx, "get", lambda *args, **kwargs: httpx.Response(200, json={"status": "ok"})
    )
    BreezeSynthesizer(Settings(data_dir=tmp_path))._start_local_server(httpx)

    assert command[0] == str(python.absolute())
    assert command[0] != str(python.resolve())
