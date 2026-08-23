import gc
from pathlib import Path
from typing import Any

from .audio import combine_wavs, split_text
from .config import Settings


class QwenSynthesizer:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._model: Any = None
        self._model_id: str | None = None

    def _dependencies(self) -> tuple[Any, Any, Any]:
        try:
            import soundfile as sf
            import torch
            from qwen_tts import Qwen3TTSModel
        except ImportError as exc:
            raise RuntimeError("Install the 'tts' extra to enable Qwen3-TTS") from exc
        return torch, sf, Qwen3TTSModel

    def _load(self, model_id: str) -> Any:
        if self._model_id == model_id and self._model is not None:
            return self._model
        self.release()
        torch, _, model_class = self._dependencies()
        dtype = getattr(torch, self.settings.tts_dtype, None)
        if dtype is None:
            raise ValueError(f"Unsupported torch dtype: {self.settings.tts_dtype}")
        kwargs: dict[str, Any] = {"device_map": self.settings.tts_device, "dtype": dtype}
        if self.settings.tts_attention:
            kwargs["attn_implementation"] = self.settings.tts_attention
        self._model = model_class.from_pretrained(model_id, **kwargs)
        self._model_id = model_id
        return self._model

    def release(self) -> None:
        self._model = None
        self._model_id = None
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
            text=reference_text, language=language, instruct=description
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        sf.write(output, wavs[0], sample_rate)

    def create_clone_prompt(self, reference_audio: Path, reference_text: str) -> Any:
        model = self._load(self.settings.voice_clone_model)
        return model.create_voice_clone_prompt(
            ref_audio=str(reference_audio), ref_text=reference_text, x_vector_only_mode=False
        )

    def synthesize_clone(
        self, text: str, output: Path, language: str, voice_clone_prompt: Any
    ) -> None:
        _, sf, _ = self._dependencies()
        model = self._load(self.settings.voice_clone_model)
        parts: list[Path] = []
        for index, chunk in enumerate(split_text(text, self.settings.chunk_chars), 1):
            wavs, sample_rate = model.generate_voice_clone(
                text=chunk, language=language, voice_clone_prompt=voice_clone_prompt
            )
            part = output.parent / f".{output.stem}.part-{index:04d}.wav"
            sf.write(part, wavs[0], sample_rate)
            parts.append(part)
        self._finish_parts(parts, output)

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
        parts: list[Path] = []
        for index, chunk in enumerate(split_text(text, self.settings.chunk_chars), 1):
            wavs, sample_rate = model.generate_custom_voice(
                text=chunk, language=language, speaker=speaker, instruct=instruction
            )
            part = output.parent / f".{output.stem}.part-{index:04d}.wav"
            sf.write(part, wavs[0], sample_rate)
            parts.append(part)
        self._finish_parts(parts, output)

    @staticmethod
    def _finish_parts(parts: list[Path], output: Path) -> None:
        try:
            combine_wavs(parts, output)
        finally:
            for part in parts:
                part.unlink(missing_ok=True)
