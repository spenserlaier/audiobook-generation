import pytest

from audiobook.crawler import crawler_args, normalize_crawler_json


def test_normalizes_flat_chapters_and_paragraphs():
    result = normalize_crawler_json(
        {"title": "Book", "chapters": [{"title": "One", "paragraphs": ["Hello", "World"]}]}
    )
    assert result[0].title == "One"
    assert result[0].text == "Hello\n\nWorld"


def test_normalizes_volume_layout():
    result = normalize_crawler_json(
        {"volumes": [{"chapters": [{"name": "Chapter A", "content": "Words"}]}]}
    )
    assert [(chapter.index, chapter.title, chapter.text) for chapter in result] == [
        (1, "Chapter A", "Words")
    ]


def test_rejects_empty_payload():
    with pytest.raises(ValueError, match="readable chapters"):
        normalize_crawler_json({"chapters": []})


def test_builds_noninteractive_v3_cli_arguments(tmp_path):
    args = crawler_args("lncrawl", "https://example.com/book", tmp_path, 4)
    assert args[:3] == ["lncrawl", "--source", "https://example.com/book"]
    assert args[args.index("--format") + 1] == "json"
    assert args[args.index("--output") + 1] == str(tmp_path)
    assert args[-2:] == ["--first", "4"]
    assert "--suppress" in args
