import json
import sqlite3
import zipfile
from types import SimpleNamespace

import pytest

from audiobook.crawler import (
    crawl,
    crawler_args,
    load_persisted_chapters,
    normalize_crawler_archive,
    normalize_crawler_json,
)


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


def test_normalizes_v4_json_zip(tmp_path):
    artifact = tmp_path / "Novel.json.zip"
    with zipfile.ZipFile(artifact, "w") as archive:
        archive.writestr("meta.json", json.dumps({"title": "Novel"}))
        archive.writestr("001/00002.json", json.dumps({"title": "Second", "content": "Later"}))
        archive.writestr("001/00001.json", json.dumps({"title": "First", "content": "Earlier"}))
    chapters = normalize_crawler_archive(artifact)
    assert [(item.title, item.text) for item in chapters] == [
        ("First", "Earlier"),
        ("Second", "Later"),
    ]


def test_loads_persisted_v4_chapters_when_artifact_is_missing(tmp_path):
    from lncrawl.utils.text_tools import text_compress

    with sqlite3.connect(tmp_path / "sqlite.db") as db:
        db.execute("CREATE TABLE novels (id TEXT, url TEXT)")
        db.execute(
            "CREATE TABLE chapters (serial INTEGER, title TEXT, novel_id TEXT, is_done INTEGER)"
        )
        db.execute("INSERT INTO novels VALUES ('novel-1', 'https://example.com/book')")
        db.execute("INSERT INTO chapters VALUES (1, 'One', 'novel-1', 1)")
    body = tmp_path / "novels" / "novel-1" / "chapters" / "000001.zst"
    body.parent.mkdir(parents=True)
    body.write_bytes(text_compress(b"Persisted body"))

    chapters = load_persisted_chapters(tmp_path, "https://example.com/book", None)
    assert [(item.title, item.text) for item in chapters] == [("One", "Persisted body")]


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
        with zipfile.ZipFile(tmp_path / "artifact.json.zip", "w") as archive:
            archive.writestr(
                "001/00001.json", json.dumps({"title": "Fresh", "content": "New text"})
            )
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("audiobook.crawler.subprocess.run", fake_run)
    chapters = crawl("audiobook-lncrawl", "https://example.com/book", tmp_path, 1)

    assert chapters[0].title == "Fresh"
    assert invocation["env"]["LNCRAWL_DATA_PATH"] == str(tmp_path.resolve())
