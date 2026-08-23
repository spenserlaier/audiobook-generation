from pathlib import Path
from typing import Any

from .audio import combine_wavs, split_text
from .config import Settings


class QwenSynthesizer:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._model: Any = None

    def _load(self) -> Any:
        if self._model is None:
            try:
                import torch
                from qwen_tts import Qwen3TTSModel
            except ImportError as exc:
                raise RuntimeError("Install the 'tts' extra to enable Qwen3-TTS") from exc
            dtype = getattr(torch, self.settings.tts_dtype, None)
            if dtype is None:
                raise ValueError(f"Unsupported torch dtype: {self.settings.tts_dtype}")
            kwargs: dict[str, Any] = {"device_map": self.settings.tts_device, "dtype": dtype}
            if self.settings.tts_attention:
                kwargs["attn_implementation"] = self.settings.tts_attention
            self._model = Qwen3TTSModel.from_pretrained(self.settings.tts_model, **kwargs)
        return self._model

    def synthesize(
        self, text: str, output: Path, language: str, speaker: str, instruction: str
    ) -> None:
        import soundfile as sf

        model = self._load()
        parts: list[Path] = []
        for index, chunk in enumerate(split_text(text, self.settings.chunk_chars), 1):
            wavs, sample_rate = model.generate_custom_voice(
                text=chunk, language=language, speaker=speaker, instruct=instruction
            )
            part = output.parent / f".{output.stem}.part-{index:04d}.wav"
            sf.write(part, wavs[0], sample_rate)
            parts.append(part)
        try:
            combine_wavs(parts, output)
        finally:
            for part in parts:
                part.unlink(missing_ok=True)
