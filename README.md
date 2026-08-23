# Audiobook Foundry

A local, UI-driven service that crawls novels supported by
[lightnovel-crawler](https://github.com/lncrawl/lightnovel-crawler), stores chapter text and
job progress in SQLite, and renders chapter WAV files with
[Qwen3-TTS](https://github.com/QwenLM/Qwen3-TTS).

## Quick start (mock mode)

Mock mode exercises the complete queue, database, UI, and audio-download flow without a crawler,
GPU, or model download.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
AUDIOBOOK_MOCK_PIPELINE=true audiobook-server
```

Open <http://127.0.0.1:8000>. Submit any valid URL. API documentation is at
<http://127.0.0.1:8000/docs>. State and generated files default to `data/`.

## Real crawler and Qwen3-TTS

Use a fresh Python 3.11 or 3.12 environment and install the optional integrations:

```bash
pip install -e '.[crawler,tts]'
audiobook-server
```

Enter a novel URL from a source supported by lightnovel-crawler. The worker runs `lncrawl crawl`
with JSON output, normalizes the resulting chapters, and synthesizes bounded text chunks. It loads
`Qwen3TTSModel` only when synthesis begins, so the normal API and tests do not import PyTorch or
download weights. Temporary chunk WAVs are joined into one WAV per chapter.

The default model is the 0.6B CustomVoice checkpoint. A CUDA GPU is strongly recommended. The first
real job downloads model weights. FlashAttention 2 is the default attention implementation and
requires compatible CUDA hardware plus `float16` or `bfloat16`; set the attention option to an empty
string to use the model's default implementation.

## Configuration

All settings use the `AUDIOBOOK_` prefix and may be placed in `.env`.

| Variable | Default | Purpose |
| --- | --- | --- |
| `AUDIOBOOK_DATA_DIR` | `data` | SQLite, crawl artifacts, and chapter audio |
| `AUDIOBOOK_CRAWLER_COMMAND` | `lncrawl` | Crawler executable |
| `AUDIOBOOK_TTS_MODEL` | `Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice` | Model ID or local path |
| `AUDIOBOOK_TTS_DEVICE` | `cuda:0` | PyTorch device map |
| `AUDIOBOOK_TTS_DTYPE` | `bfloat16` | PyTorch dtype name |
| `AUDIOBOOK_TTS_ATTENTION` | `flash_attention_2` | Attention implementation |
| `AUDIOBOOK_CHUNK_CHARS` | `1200` | Maximum text characters per synthesis call |
| `AUDIOBOOK_WORKER_COUNT` | `1` | Concurrent background jobs; one is safest for GPU memory |
| `AUDIOBOOK_MOCK_PIPELINE` | `false` | Use deterministic local chapters and short tone WAVs |

Jobs move through `queued`, `crawling`, `synthesizing`, `completed`, or `failed`. Progress, errors,
normalized chapter text, and audio links persist in SQLite. On server restart, queued or interrupted
jobs are submitted again. The crawler and synthesizer may repeat work for an interrupted job, but
finished database state is never mistaken for a completed file.

## Development

```bash
pytest
ruff check .
```

## Responsible use

Only download and synthesize material you are legally allowed to access and reproduce. Site terms,
copyright law, and text-to-speech/model licenses still apply. This project is designed for local,
personal use; it does not bypass authentication, paywalls, or crawler source restrictions. Generated
voices should not be represented as recordings of real people.
