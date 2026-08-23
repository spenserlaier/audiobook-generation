import json
import os
import sqlite3
import subprocess
import zipfile
from pathlib import Path
from typing import Any

from .models import Chapter


def _text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        return "\n\n".join(filter(None, (_text(item) for item in value)))
    if isinstance(value, dict):
        for key in ("text", "content", "body", "paragraphs"):
            if key in value:
                return _text(value[key])
    return ""


def normalize_crawler_json(payload: Any) -> list[Chapter]:
    """Accept common lightnovel-crawler JSON layouts across released versions."""
    roots = payload if isinstance(payload, list) else [payload]
    candidates: list[Any] = []
    for root in roots:
        if not isinstance(root, dict):
            continue
        if isinstance(root.get("chapters"), list):
            candidates.extend(root["chapters"])
        for volume in root.get("volumes", []) if isinstance(root.get("volumes"), list) else []:
            if isinstance(volume, dict) and isinstance(volume.get("chapters"), list):
                candidates.extend(volume["chapters"])
        if any(key in root for key in ("body", "content", "text")):
            candidates.append(root)
    chapters: list[Chapter] = []
    for item in candidates:
        if not isinstance(item, dict):
            continue
        body = _text(item)
        if not body:
            continue
        title = str(item.get("title") or item.get("name") or f"Chapter {len(chapters) + 1}")
        chapters.append(Chapter(index=len(chapters) + 1, title=title.strip(), text=body))
    if not chapters:
        raise ValueError("Crawler JSON did not contain any readable chapters")
    return chapters


def normalize_crawler_archive(path: Path) -> list[Chapter]:
    """Read lncrawl 4.x's JSON ZIP: metadata plus one JSON file per chapter."""
    with zipfile.ZipFile(path) as archive:
        names = sorted(
            name
            for name in archive.namelist()
            if name.endswith(".json") and Path(name).name != "meta.json"
        )
        documents = [json.loads(archive.read(name).decode("utf-8")) for name in names]
    return normalize_crawler_json(documents)


def load_persisted_chapters(state_dir: Path, url: str, limit: int | None) -> list[Chapter]:
    """Fall back to successfully persisted lncrawl rows and compressed chapter bodies."""
    database = state_dir / "sqlite.db"
    if not database.is_file():
        return []
    with sqlite3.connect(database) as db:
        rows = db.execute(
            """SELECT c.serial, c.title, c.novel_id
               FROM chapters c JOIN novels n ON n.id = c.novel_id
               WHERE n.url = ? AND c.is_done = 1 ORDER BY c.serial""",
            (url,),
        ).fetchall()
    if limit:
        rows = rows[:limit]
    try:
        from lncrawl.utils.text_tools import text_decompress
    except ImportError:
        return []
    chapters: list[Chapter] = []
    for serial, title, novel_id in rows:
        path = state_dir / "novels" / novel_id / "chapters" / f"{serial:06}.zst"
        if not path.is_file():
            continue
        body = text_decompress(path.read_bytes()).decode("utf-8").strip()
        if body:
            chapters.append(Chapter(index=len(chapters) + 1, title=title, text=body))
    return chapters


def crawler_args(command: str, url: str, limit: int | None) -> list[str]:
    """Build arguments for the lightnovel-crawler 4.x CLI."""
    args = [command, "crawl", url, "--format", "json", "--noin"]
    args += ["--first", str(limit)] if limit else ["--all"]
    return args


def crawl(command: str, url: str, destination: Path, limit: int | None) -> list[Chapter]:
    destination.mkdir(parents=True, exist_ok=True)
    before = {
        path: (path.stat().st_mtime_ns, path.stat().st_size)
        for path in destination.rglob("*")
        if path.is_file() and (path.suffix == ".json" or path.name.endswith(".json.zip"))
    }
    args = crawler_args(command, url, limit)
    environment = {**os.environ, "LNCRAWL_DATA_PATH": str(destination.resolve())}
    result = subprocess.run(
        args,
        cwd=destination,
        env=environment,
        text=True,
        capture_output=True,
        timeout=3600,
    )
    if result.returncode:
        detail = (result.stderr or result.stdout).strip()[-2000:]
        raise RuntimeError(f"lightnovel-crawler failed ({result.returncode}): {detail}")
    files = [
        path
        for path in destination.rglob("*")
        if path.is_file() and (path.suffix == ".json" or path.name.endswith(".json.zip"))
        if before.get(path) != (path.stat().st_mtime_ns, path.stat().st_size)
    ]
    files.sort(key=lambda path: path.stat().st_mtime_ns, reverse=True)
    errors: list[str] = []
    for path in files:
        try:
            if zipfile.is_zipfile(path):
                chapters = normalize_crawler_archive(path)
            else:
                chapters = normalize_crawler_json(json.loads(path.read_text(encoding="utf-8")))
            return chapters[:limit] if limit else chapters
        except (
            OSError,
            UnicodeDecodeError,
            zipfile.BadZipFile,
            json.JSONDecodeError,
            ValueError,
        ) as exc:
            errors.append(f"{path.name}: {exc}")
    chapters = load_persisted_chapters(destination, url, limit)
    if chapters:
        return chapters
    raise RuntimeError(
        "Crawler completed but no usable JSON was found"
        + (": " + "; ".join(errors) if errors else "")
    )
