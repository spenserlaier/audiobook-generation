import json
from types import SimpleNamespace

import pytest

from audiobook.crawler import crawl, crawler_args, normalize_crawler_json


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


def test_builds_noninteractive_v4_cli_arguments(tmp_path):
    args = crawler_args("audiobook-lncrawl", "https://example.com/book", 4)
    assert args[:4] == [
        "audiobook-lncrawl",
        "crawl",
        "https://example.com/book",
        "--format",
    ]
    assert args[args.index("--format") + 1] == "json"
    assert args[-2:] == ["--first", "4"]
    assert "--noin" in args


def test_crawl_uses_project_state_and_new_json(monkeypatch, tmp_path):
    (tmp_path / "stale.json").write_text('{"chapters": []}')
    invocation = {}

    def fake_run(args, **kwargs):
        invocation.update(args=args, **kwargs)
        (tmp_path / "artifact.json").write_text(
            json.dumps({"chapters": [{"title": "Fresh", "body": "New text"}]})
        )
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("audiobook.crawler.subprocess.run", fake_run)
    chapters = crawl("audiobook-lncrawl", "https://example.com/book", tmp_path, 1)

    assert chapters[0].title == "Fresh"
    assert invocation["env"]["LNCRAWL_DATA_PATH"] == str(tmp_path.resolve())
