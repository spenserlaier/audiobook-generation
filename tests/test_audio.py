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
