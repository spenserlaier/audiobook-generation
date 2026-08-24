from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile, is_zipfile


@dataclass
class ArchiveState:
    state: str = "idle"
    completed_files: int = 0
    total_files: int = 0
    size_bytes: int = 0
    error: str | None = None


class ArchiveManager:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self._lock = threading.Lock()
        self._states: dict[str, ArchiveState] = {}

    def _paths(self, job_id: str) -> tuple[Path, Path]:
        directory = self.data_dir / "jobs" / job_id
        return directory / "audiobook.zip", directory / ".audiobook.zip.part"

    def status(self, job_id: str, total_files: int = 0) -> ArchiveState:
        archive, _ = self._paths(job_id)
        with self._lock:
            current = self._states.get(job_id)
            if current and current.state == "preparing":
                return ArchiveState(**vars(current))
            if archive.is_file() and is_zipfile(archive):
                ready = ArchiveState(
                    state="ready",
                    completed_files=total_files,
                    total_files=total_files,
                    size_bytes=archive.stat().st_size,
                )
                self._states[job_id] = ready
                return ArchiveState(**vars(ready))
            if current and current.state == "failed":
                return ArchiveState(**vars(current))
            return ArchiveState(total_files=total_files)

    def prepare(self, job_id: str, files: list[Path]) -> ArchiveState:
        current = self.status(job_id, len(files))
        if current.state in {"preparing", "ready"}:
            return current
        state = ArchiveState(state="preparing", total_files=len(files))
        with self._lock:
            # Recheck under the lock so simultaneous requests only launch one thread.
            existing = self._states.get(job_id)
            if existing and existing.state == "preparing":
                return ArchiveState(**vars(existing))
            self._states[job_id] = state
        thread = threading.Thread(
            target=self._build,
            args=(job_id, files),
            name=f"audiobook-archive-{job_id[:8]}",
            daemon=True,
        )
        thread.start()
        return ArchiveState(**vars(state))

    def is_preparing(self, job_id: str) -> bool:
        with self._lock:
            state = self._states.get(job_id)
            return bool(state and state.state == "preparing")

    def _build(self, job_id: str, files: list[Path]) -> None:
        archive, temporary = self._paths(job_id)
        try:
            archive.parent.mkdir(parents=True, exist_ok=True)
            temporary.unlink(missing_ok=True)
            if archive.exists() and not is_zipfile(archive):
                archive.unlink()
            with ZipFile(temporary, "w", compression=ZIP_DEFLATED) as bundle:
                for completed, path in enumerate(files, 1):
                    if not path.is_file():
                        raise FileNotFoundError(f"Chapter audio is missing: {path.name}")
                    bundle.write(path, arcname=path.name)
                    with self._lock:
                        self._states[job_id].completed_files = completed
                        self._states[job_id].size_bytes = temporary.stat().st_size
            # Opening the central directory catches incomplete or malformed output.
            with ZipFile(temporary) as bundle:
                if len(bundle.infolist()) != len(files):
                    raise BadZipFile("Archive does not contain every chapter")
            temporary.replace(archive)
            with self._lock:
                state = self._states[job_id]
                state.state = "ready"
                state.size_bytes = archive.stat().st_size
        except Exception as exc:
            temporary.unlink(missing_ok=True)
            with self._lock:
                self._states[job_id] = ArchiveState(
                    state="failed",
                    total_files=len(files),
                    error=f"{type(exc).__name__}: {exc}",
                )
