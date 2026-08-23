import wave

from audiobook.audio import combine_wavs, split_text, write_mock_wav


def test_split_text_respects_limit_and_preserves_words():
    text = "First short sentence. Second short sentence.\n\nA new paragraph."
    chunks = split_text(text, 30)
    assert all(0 < len(chunk) <= 30 for chunk in chunks)
    assert " ".join(" ".join(chunks).split()) == " ".join(text.split())


def test_mock_wavs_can_be_combined(tmp_path):
    first, second, output = tmp_path / "1.wav", tmp_path / "2.wav", tmp_path / "out.wav"
    write_mock_wav(first, "one")
    write_mock_wav(second, "two")
    combine_wavs([first, second], output)
    with wave.open(str(output), "rb") as wav:
        assert wav.getnframes() > 0
        assert wav.getframerate() == 16_000


def test_combines_chunks_with_different_durations(tmp_path):
    short, long, output = tmp_path / "short.wav", tmp_path / "long.wav", tmp_path / "out.wav"
    write_mock_wav(short, "short")
    write_mock_wav(long, "a much longer passage " * 30)
    with wave.open(str(short), "rb") as wav:
        short_frames = wav.getnframes()
    with wave.open(str(long), "rb") as wav:
        long_frames = wav.getnframes()
    assert short_frames != long_frames

    combine_wavs([short, long], output)

    with wave.open(str(output), "rb") as wav:
        assert wav.getnframes() == short_frames + long_frames
