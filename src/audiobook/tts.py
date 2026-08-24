import gc
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any

from .audio import combine_wavs, split_text
from .config import Settings


def resolve_attention(requested: str, flash_available: bool | None = None) -> str | None:
    choice = requested.strip().lower()
    if not choice:
        return None
    if choice != "auto":
        return choice
    if flash_available is None:
        flash_available = importlib.util.find_spec("flash_attn") is not None
    return "flash_attention_2" if flash_available else "sdpa"


class QwenSynthesizer:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._model: Any = None
        self._model_id: str | None = None

    def _dependencies(self) -> tuple[Any, Any, Any]:
        try:
            import soundfile as sf
            import torch
        except ImportError as exc:
            raise RuntimeError("Install a TTS extra to enable Qwen3-TTS") from exc

        if self.settings.tts_backend == "faster":
            try:
                from faster_qwen3_tts import FasterQwen3TTS
            except ImportError as exc:
                raise RuntimeError(
                    "Install the 'tts-faster' extra to use the faster TTS backend"
                ) from exc
            model_class = FasterQwen3TTS
        else:
            try:
                from qwen_tts import Qwen3TTSModel
            except ImportError as exc:
                raise RuntimeError(
                    "Install the 'tts' extra to use the official TTS backend"
                ) from exc
            model_class = Qwen3TTSModel
        return torch, sf, model_class

    def _load(self, model_id: str) -> Any:
        if self._model_id == model_id and self._model is not None:
            return self._model
        self.release()
        torch, _, model_class = self._dependencies()
        dtype = getattr(torch, self.settings.tts_dtype, None)
        if dtype is None:
            raise ValueError(f"Unsupported torch dtype: {self.settings.tts_dtype}")
        if self.settings.tts_backend == "faster":
            if not torch.cuda.is_available():
                raise RuntimeError("The faster TTS backend requires an available CUDA GPU")
            kwargs: dict[str, Any] = {
                "device": self.settings.tts_device,
                "dtype": dtype,
                "attn_implementation": "sdpa",
                "max_seq_len": self.settings.tts_max_seq_len,
            }
        else:
            kwargs = {"device_map": self.settings.tts_device, "dtype": dtype}
            attention = resolve_attention(self.settings.tts_attention)
            if attention:
                kwargs["attn_implementation"] = attention
        self._model = model_class.from_pretrained(model_id, **kwargs)
        self._model_id = model_id
        return self._model

    def release(self) -> None:
        model = self._model
        self._model = None
        self._model_id = None
        del model
        gc.collect()
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except ImportError:
            pass

    def design_voice(
        self, reference_text: str, description: str, language: str, output: Path
    ) -> None:
        _, sf, _ = self._dependencies()
        model = self._load(self.settings.voice_design_model)
        wavs, sample_rate = model.generate_voice_design(
            text=reference_text,
            language=language,
            instruct=description,
            **self._generation_options(),
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        sf.write(output, wavs[0], sample_rate)

    def create_clone_prompt(self, reference_audio: Path, reference_text: str) -> Any:
        model = self._load(self.settings.voice_clone_model)
        prompt_model = model.model if self.settings.tts_backend == "faster" else model
        return prompt_model.create_voice_clone_prompt(
            ref_audio=str(reference_audio), ref_text=reference_text, x_vector_only_mode=False
        )

    def _generation_options(self, attempt: int = 0) -> dict[str, int | float | bool]:
        options: dict[str, int | float | bool] = {
            "max_new_tokens": self.settings.tts_max_new_tokens,
            "do_sample": True,
            "top_k": self.settings.tts_top_k,
            "top_p": self.settings.tts_top_p,
            "temperature": max(0.6, self.settings.tts_temperature - 0.05 * attempt),
            "repetition_penalty": self.settings.tts_repetition_penalty + 0.02 * attempt,
        }
        # faster-qwen3-tts exposes only the main-talker sampling arguments.
        # The official backend forwards its extra kwargs to the subtalker model.
        if self.settings.tts_backend == "official":
            options.update(
                {
                    "subtalker_dosample": True,
                    "subtalker_top_k": self.settings.tts_top_k,
                    "subtalker_top_p": self.settings.tts_top_p,
                    "subtalker_temperature": max(
                        0.6, self.settings.tts_subtalker_temperature - 0.05 * attempt
                    ),
                }
            )
        return options

    @staticmethod
    def _duration_limit(text: str) -> float:
        # Roughly 150 words/minute, with generous headroom for dramatic narration.
        expected = max(1, len(text.split())) / 2.5
        return max(20.0, expected * 1.75 + 10.0)

    def _generate_with_retries(self, text: str, generate: Any) -> tuple[Any, int, dict[str, Any]]:
        attempts: list[dict[str, Any]] = []
        candidates: list[tuple[float, Any, int]] = []
        duration_limit = self._duration_limit(text)
        for attempt in range(self.settings.tts_quality_retries + 1):
            options = self._generation_options(attempt)
            wavs, sample_rate = generate(options)
            wav = wavs[0]
            duration = len(wav) / sample_rate
            rejected = duration > duration_limit
            attempts.append(
                {
                    "attempt": attempt + 1,
                    "duration_seconds": round(duration, 3),
                    "duration_limit_seconds": round(duration_limit, 3),
                    "rejected_as_runaway": rejected,
                    "temperature": options["temperature"],
                    "repetition_penalty": options["repetition_penalty"],
                }
            )
            candidates.append((duration, wav, sample_rate))
            if not rejected:
                return wav, sample_rate, {"attempts": attempts, "warning": None}
        _, wav, sample_rate = min(candidates, key=lambda item: item[0])
        return wav, sample_rate, {
            "attempts": attempts,
            "warning": "All candidates exceeded the conservative duration limit; shortest retained",
        }

    @staticmethod
    def _write_quality_manifest(output: Path, chunks: list[dict[str, Any]]) -> None:
        manifest = output.with_suffix(".quality.json")
        manifest.write_text(json.dumps({"chunks": chunks}, indent=2), encoding="utf-8")

    def synthesize_clone(
        self, text: str, output: Path, language: str, voice_clone_prompt: Any
    ) -> None:
        _, sf, _ = self._dependencies()
        model = self._load(self.settings.voice_clone_model)
        output.parent.mkdir(parents=True, exist_ok=True)
        parts: list[Path] = []
        quality: list[dict[str, Any]] = []
        for index, chunk in enumerate(split_text(text, self.settings.chunk_chars), 1):
            wav, sample_rate, result = self._generate_with_retries(
                chunk,
                lambda options, chunk=chunk: model.generate_voice_clone(
                    text=chunk,
                    language=language,
                    voice_clone_prompt=voice_clone_prompt,
                    **options,
                ),
            )
            part = output.parent / f".{output.stem}.part-{index:04d}.wav"
            sf.write(part, wav, sample_rate)
            parts.append(part)
            quality.append(
                {
                    "index": index,
                    "text_sha256": hashlib.sha256(chunk.encode()).hexdigest(),
                    **result,
                }
            )
        self._finish_parts(parts, output)
        self._write_quality_manifest(output, quality)

    def synthesize_custom(
        self,
        text: str,
        output: Path,
        language: str,
        speaker: str,
        instruction: str,
    ) -> None:
        _, sf, _ = self._dependencies()
        model = self._load(self.settings.tts_model)
        output.parent.mkdir(parents=True, exist_ok=True)
        parts: list[Path] = []
        quality: list[dict[str, Any]] = []
        for index, chunk in enumerate(split_text(text, self.settings.chunk_chars), 1):
            wav, sample_rate, result = self._generate_with_retries(
                chunk,
                lambda options, chunk=chunk: model.generate_custom_voice(
                    text=chunk,
                    language=language,
                    speaker=speaker,
                    instruct=instruction,
                    **options,
                ),
            )
            part = output.parent / f".{output.stem}.part-{index:04d}.wav"
            sf.write(part, wav, sample_rate)
            parts.append(part)
            quality.append(
                {
                    "index": index,
                    "text_sha256": hashlib.sha256(chunk.encode()).hexdigest(),
                    **result,
                }
            )
        self._finish_parts(parts, output)
        self._write_quality_manifest(output, quality)

    @staticmethod
    def _finish_parts(parts: list[Path], output: Path) -> None:
        try:
            combine_wavs(parts, output)
        finally:
            for part in parts:
                part.unlink(missing_ok=True)
