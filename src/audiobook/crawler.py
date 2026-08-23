import json
import subprocess
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


def crawler_args(command: str, url: str, destination: Path, limit: int | None) -> list[str]:
    """Build arguments for the pinned, database-free lightnovel-crawler 3.x CLI."""
    args = [
        command,
        "--source",
        url,
        "--format",
        "json",
        "--output",
        str(destination),
        "--suppress",
        "--close-directly",
    ]
    args += ["--first", str(limit)] if limit else ["--all"]
    return args


def crawl(command: str, url: str, destination: Path, limit: int | None) -> list[Chapter]:
    destination.mkdir(parents=True, exist_ok=True)
    args = crawler_args(command, url, destination, limit)
    result = subprocess.run(args, cwd=destination, text=True, capture_output=True, timeout=3600)
    if result.returncode:
        detail = (result.stderr or result.stdout).strip()[-2000:]
        raise RuntimeError(f"lightnovel-crawler failed ({result.returncode}): {detail}")
    files = sorted(destination.rglob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    errors: list[str] = []
    for path in files:
        try:
            chapters = normalize_crawler_json(json.loads(path.read_text(encoding="utf-8")))
            return chapters[:limit] if limit else chapters
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            errors.append(f"{path.name}: {exc}")
    raise RuntimeError(
        "Crawler completed but no usable JSON was found"
        + (": " + "; ".join(errors) if errors else "")
    )
