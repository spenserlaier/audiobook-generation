import math
import struct
import wave
from pathlib import Path


def split_text(text: str, limit: int) -> list[str]:
    if limit < 1:
        raise ValueError("chunk limit must be positive")
    paragraphs = [part.strip() for part in text.splitlines() if part.strip()]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        while len(paragraph) > limit:
            cut = max(paragraph.rfind(mark, 0, limit + 1) for mark in (". ", "! ", "? ", "; ", " "))
            cut = cut + 1 if cut > 0 else limit
            piece, paragraph = paragraph[:cut].strip(), paragraph[cut:].strip()
            if current:
                chunks.append(current)
                current = ""
            if piece:
                chunks.append(piece)
        proposed = f"{current}\n\n{paragraph}" if current else paragraph
        if len(proposed) <= limit:
            current = proposed
        else:
            if current:
                chunks.append(current)
            current = paragraph
    if current:
        chunks.append(current)
    return chunks


def write_mock_wav(path: Path, text: str, sample_rate: int = 16_000) -> None:
    duration = min(2.0, max(0.15, len(text) / 500))
    frames = int(sample_rate * duration)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as output:
        output.setparams((1, 2, sample_rate, frames, "NONE", "not compressed"))
        output.writeframes(
            b"".join(
                struct.pack("<h", int(900 * math.sin(2 * math.pi * 220 * i / sample_rate)))
                for i in range(frames)
            )
        )


def combine_wavs(parts: list[Path], output_path: Path) -> None:
    if not parts:
        raise ValueError("No audio chunks to combine")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(parts[0]), "rb") as first:
        params = first.getparams()
        encoding = (params.nchannels, params.sampwidth, params.framerate, params.comptype)
    with wave.open(str(output_path), "wb") as target:
        target.setparams(params)
        for part in parts:
            with wave.open(str(part), "rb") as source:
                source_params = source.getparams()
                source_encoding = (
                    source_params.nchannels,
                    source_params.sampwidth,
                    source_params.framerate,
                    source_params.comptype,
                )
                if source_encoding != encoding:
                    raise ValueError("Audio chunks use incompatible WAV formats")
                target.writeframes(source.readframes(source.getnframes()))
