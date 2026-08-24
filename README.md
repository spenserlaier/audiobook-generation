# Audiobook Foundry

A local, UI-driven service that crawls novels supported by
[lightnovel-crawler](https://github.com/lncrawl/lightnovel-crawler), stores chapter text and
job progress in SQLite, designs a reusable narrative voice, and renders chapter WAV files with
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
pip install -e '.[crawler,tts-faster]'
audiobook-server
```

The CUDA-graph-powered `faster-qwen3-tts` backend is the default. To use the official backend instead:

```bash
pip install -e '.[crawler,tts]'
AUDIOBOOK_TTS_BACKEND=official audiobook-server
```

`faster-qwen3-tts` is pinned to 0.3.2 so upgrades cannot silently change its CUDA graph or prompt
behavior. It requires PyTorch 2.5.1 or newer and an NVIDIA CUDA GPU. Use Python 3.11 or 3.12 for
the GPU environment; these are the versions advertised by the package and avoid relying on the
project's current Python 3.14 compatibility by accident.

Enter a novel URL from a source supported by lightnovel-crawler. The worker runs its noninteractive
CLI with JSON output, normalizes the resulting chapters, and synthesizes bounded text chunks. A narrow
project-owned launcher corrects a 4.14 SQLite migration default before delegating to the official CLI;
it does not modify the installed package or user-level crawler database. Crawler state and its source
cache live under `AUDIOBOOK_DATA_DIR/crawler-state`. It loads
`Qwen3TTSModel` only when synthesis begins, so the normal API and tests do not import PyTorch or
download weights. Temporary chunk WAVs are joined into one WAV per chapter.
The chapter scope can explicitly target all chapters or only the first requested number.

The default workflow targets an RTX 4090: the 1.7B VoiceDesign checkpoint generates a short voice
reference, then the 1.7B Base checkpoint clones it for every chapter. VoiceDesign is released from
memory before Base is loaded so the checkpoints do not occupy VRAM together. The generated reference
is playable in the job UI. The optional built-in-voice workflow uses the 1.7B CustomVoice checkpoint.

A CUDA GPU is strongly recommended. The first real job downloads the selected model weights.
Attention selection defaults to `auto`: FlashAttention 2 is used when `flash_attn` is installed,
otherwise PyTorch SDPA is used. SDPA works on the RTX 4090 without compiling an additional CUDA
extension. An explicit `flash_attention_2` setting requires a compatible `flash-attn` installation
plus `float16` or `bfloat16`.

The `faster` backend uses SDPA with a fixed-size CUDA-graph cache; `AUDIOBOOK_TTS_ATTENTION` does not
apply to it. Its model is released after every job by default to return VRAM to the desktop. Set
`AUDIOBOOK_TTS_RELEASE_AFTER_JOB=false` only after stability testing if keeping the model hot between
jobs matters more than freeing VRAM. Real GPU mode rejects worker counts above one because model
loading and generation share a single GPU model instance.

The service cannot protect the desktop from a kernel/driver-level GPU hang. Before a long run, verify
that `nvidia-smi` works, that the PyTorch CUDA build is supported by the installed NVIDIA driver, and
that no display instability appears in a short one-chunk smoke test. A separate non-display GPU is
the safest arrangement for unattended generation.

## Configuration

All settings use the `AUDIOBOOK_` prefix and may be placed in `.env`.

| Variable | Default | Purpose |
| --- | --- | --- |
| `AUDIOBOOK_DATA_DIR` | `data` | SQLite, crawl artifacts, and chapter audio |
| `AUDIOBOOK_CRAWLER_COMMAND` | `audiobook-lncrawl` | Crawler compatibility launcher |
| `AUDIOBOOK_FFMPEG_COMMAND` | `ffmpeg` | FFmpeg executable used for MP3 archive exports |
| `AUDIOBOOK_MP3_BITRATE` | `128k` | MP3 archive export bitrate |
| `AUDIOBOOK_MP3_WORKERS` | `4` | Concurrent single-threaded FFmpeg chapter encoders |
| `AUDIOBOOK_TTS_MODEL` | `Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice` | Optional built-in voice model |
| `AUDIOBOOK_VOICE_DESIGN_MODEL` | `Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign` | Narrative voice design model |
| `AUDIOBOOK_VOICE_CLONE_MODEL` | `Qwen/Qwen3-TTS-12Hz-1.7B-Base` | Designed-voice cloning model |
| `AUDIOBOOK_TTS_BACKEND` | `faster` | `faster` CUDA graphs or the `official` backend |
| `AUDIOBOOK_TTS_DEVICE` | `cuda:0` | PyTorch device map |
| `AUDIOBOOK_TTS_DTYPE` | `bfloat16` | PyTorch dtype name |
| `AUDIOBOOK_TTS_ATTENTION` | `auto` | `flash_attention_2` when installed, otherwise `sdpa` |
| `AUDIOBOOK_TTS_MAX_SEQ_LEN` | `2048` | Static cache length used by the faster backend |
| `AUDIOBOOK_TTS_MAX_NEW_TOKENS` | `2048` | Per-chunk codec-token generation ceiling |
| `AUDIOBOOK_TTS_TEMPERATURE` | `0.75` | Main-talker sampling temperature |
| `AUDIOBOOK_TTS_TOP_P` | `0.95` | Nucleus sampling threshold |
| `AUDIOBOOK_TTS_TOP_K` | `50` | Top-k sampling limit |
| `AUDIOBOOK_TTS_REPETITION_PENALTY` | `1.08` | Codec-token repetition penalty |
| `AUDIOBOOK_TTS_SUBTALKER_TEMPERATURE` | `0.75` | Subtalker sampling temperature |
| `AUDIOBOOK_TTS_QUALITY_RETRIES` | `2` | Retries for abnormally long chunk output |
| `AUDIOBOOK_CHUNK_CHARS` | `1200` | Maximum text characters per synthesis call |
| `AUDIOBOOK_WORKER_COUNT` | `1` | Concurrent background jobs; one is safest for GPU memory |
| `AUDIOBOOK_TTS_RELEASE_AFTER_JOB` | `true` | Release model and cached VRAM after each job |
| `AUDIOBOOK_MOCK_PIPELINE` | `false` | Use deterministic local chapters and short tone WAVs |

The UI can generate reusable narrator previews before a novel is submitted. Completed chapters can
be played or downloaded individually. Whole-book ZIPs are prepared by a singleton background task,
show chapter-count progress, and become downloadable only after an atomic finalization step. Repeated
requests reuse the active task or completed archive instead of restarting it. MP3 is the default ZIP
format; WAV export remains available, and both formats can coexist for the same job. MP3 export uses
FFmpeg to encode each source chapter without replacing the original WAV.
Jobs can be hidden from the main list without affecting their files. The separate Storage view shows
disk usage per run and can permanently remove its generated WAV, voice-reference, and ZIP files while
retaining the job history in SQLite. Bulk controls clear the job list or all finished-run artifacts;
active generation is never cancelled or deleted. Chapter lists start collapsed and fetch 50 records
at a time when expanded, keeping large libraries responsive.
Normalized chapter text remains in SQLite after generated files are cleared. A completed or cancelled
job with saved chapters can be regenerated into a new configurable job, using a different title,
chapter limit, language, or voice without running the crawler again.
While the crawler is running, the job stage reports downloaded and discovered chapter counts from
the crawler's persisted state instead of remaining at an unexplained fixed percentage.

Active jobs have a Cancel control. Cancelling a crawl terminates its crawler process; synthesis stops
between chapters. Clear queue cancels all jobs still waiting for the worker. If the server stops during
a crawl or synthesis, that interrupted job is marked cancelled on restart instead of automatically
blocking the worker again.

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
