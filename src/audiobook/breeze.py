"""Client for the official Breeze TTS 2 local streaming API."""

import hashlib
import json
import wave
from pathlib import Path

from .audio import combine_wavs, split_text
from .config import Settings


class BreezeSynthesizer:
    def __init__(self, settings: Settings):
        self.settings = settings

    def release(self) -> None:
        # The separately managed Breeze server owns its model lifetime.
        pass

    def _speech(
        self,
        text: str,
        *,
        instruction: str = "",
        reference_audio: Path | None = None,
        reference_text: str = "",
        seed: int,
    ) -> tuple[bytes, int]:
        try:
            import httpx
        except ImportError as exc:
            raise RuntimeError("Install the 'breeze' extra to use Breeze TTS") from exc

        data = {
            "text": text,
            "cfg_scale": str(self.settings.breeze_cfg_scale if instruction.strip() else 1.0),
            "seed": str(seed),
        }
        if instruction.strip():
            data["instruction"] = instruction.strip()
        if reference_audio is not None:
            if not reference_text.strip():
                raise ValueError("Breeze reference audio requires its exact transcript")
            data["ref_text"] = reference_text.strip()

        url = f"{self.settings.breeze_api_url.rstrip('/')}/v1/audio/speech"
        timeout = httpx.Timeout(
            connect=5.0, read=self.settings.breeze_timeout_seconds, write=30.0, pool=5.0
        )
        try:
            with httpx.Client(timeout=timeout) as client:
                if reference_audio is None:
                    response_context = client.stream("POST", url, data=data)
                else:
                    with reference_audio.open("rb") as source:
                        response_context = client.stream(
                            "POST",
                            url,
                            data=data,
                            files={"ref_audio": (reference_audio.name, source, "audio/wav")},
                        )
                        with response_context as response:
                            return self._read_pcm(response)
                with response_context as response:
                    return self._read_pcm(response)
        except httpx.RequestError as exc:
            raise RuntimeError(f"Breeze API request failed at {url}: {exc}") from exc

    @staticmethod
    def _read_pcm(response) -> tuple[bytes, int]:
        if response.status_code != 200:
            detail = response.read().decode("utf-8", errors="replace")[:500]
            raise RuntimeError(f"Breeze API returned HTTP {response.status_code}: {detail}")
        if response.headers.get("x-sample-format") != "s16le":
            raise RuntimeError("Breeze API returned an unsupported sample format")
        try:
            sample_rate = int(response.headers["x-sample-rate"])
        except (KeyError, ValueError) as exc:
            raise RuntimeError("Breeze API did not return a valid sample rate") from exc
        if sample_rate <= 0:
            raise RuntimeError("Breeze API returned an invalid sample rate")
        pcm = b"".join(response.iter_bytes())
        if not pcm or len(pcm) % 2:
            raise RuntimeError("Breeze API returned empty or incomplete PCM audio")
        return pcm, sample_rate

    @staticmethod
    def _write_wav(output: Path, pcm: bytes, sample_rate: int) -> None:
        output.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(output), "wb") as target:
            target.setparams((1, 2, sample_rate, 0, "NONE", "not compressed"))
            target.writeframes(pcm)

    def design_voice(
        self, reference_text: str, description: str, language: str, output: Path
    ) -> None:
        pcm, sample_rate = self._speech(
            reference_text, instruction=description, seed=self.settings.breeze_seed
        )
        self._write_wav(output, pcm, sample_rate)

    @staticmethod
    def create_clone_prompt(reference_audio: Path, reference_text: str) -> tuple[Path, str]:
        if not reference_audio.is_file():
            raise FileNotFoundError(reference_audio)
        if not reference_text.strip():
            raise ValueError("Breeze reference audio requires its exact transcript")
        return reference_audio, reference_text

    def synthesize_clone(
        self,
        text: str,
        output: Path,
        language: str,
        voice_clone_prompt: tuple[Path, str],
        instruction: str = "",
    ) -> None:
        reference_audio, reference_text = voice_clone_prompt
        parts: list[Path] = []
        quality: list[dict] = []
        try:
            for index, chunk in enumerate(split_text(text, self.settings.breeze_chunk_chars), 1):
                limit = max(20.0, len(chunk.split()) / 2.5 * 1.75 + 10.0)
                attempts = []
                candidates = []
                for attempt in range(self.settings.tts_quality_retries + 1):
                    seed = self.settings.breeze_seed + index * 100 + attempt
                    pcm, rate = self._speech(
                        chunk,
                        instruction=instruction,
                        reference_audio=reference_audio,
                        reference_text=reference_text,
                        seed=seed,
                    )
                    duration = len(pcm) / (2 * rate)
                    rejected = duration > limit
                    attempts.append(
                        {
                            "attempt": attempt + 1,
                            "seed": seed,
                            "duration_seconds": round(duration, 3),
                            "duration_limit_seconds": round(limit, 3),
                            "rejected_as_runaway": rejected,
                        }
                    )
                    candidates.append((duration, pcm, rate))
                    if not rejected:
                        break
                _, pcm, rate = min(candidates, key=lambda item: item[0])
                part = output.parent / f".{output.stem}.part-{index:04d}.wav"
                self._write_wav(part, pcm, rate)
                parts.append(part)
                quality.append(
                    {
                        "index": index,
                        "text_sha256": hashlib.sha256(chunk.encode()).hexdigest(),
                        "attempts": attempts,
                        "warning": (
                            "All candidates exceeded the duration limit; shortest retained"
                            if all(item["rejected_as_runaway"] for item in attempts)
                            else None
                        ),
                    }
                )
            combine_wavs(parts, output)
            output.with_suffix(".quality.json").write_text(
                json.dumps({"chunks": quality}, indent=2), encoding="utf-8"
            )
        finally:
            for part in parts:
                part.unlink(missing_ok=True)
