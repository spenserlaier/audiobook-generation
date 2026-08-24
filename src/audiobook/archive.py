from __future__ import annotations

import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZIP_STORED, BadZipFile, ZipFile, is_zipfile


@dataclass
class ArchiveState:
    state: str = "idle"
    completed_files: int = 0
    total_files: int = 0
    size_bytes: int = 0
    error: str | None = None


class ArchiveManager:
    def __init__(self, data_dir: Path, ffmpeg_command: str = "ffmpeg", mp3_bitrate: str = "128k"):
        self.data_dir = data_dir
        self.ffmpeg_command = ffmpeg_command
        self.mp3_bitrate = mp3_bitrate
        self._lock = threading.Lock()
        self._states: dict[tuple[str, str], ArchiveState] = {}

    def _paths(self, job_id: str, output_format: str) -> tuple[Path, Path]:
        directory = self.data_dir / "jobs" / job_id
        name = "audiobook-mp3.zip" if output_format == "mp3" else "audiobook.zip"
        return directory / name, directory / f".{name}.part"

    def archive_path(self, job_id: str, output_format: str) -> Path:
        return self._paths(job_id, output_format)[0]

    def status(self, job_id: str, output_format: str, total_files: int = 0) -> ArchiveState:
        archive, _ = self._paths(job_id, output_format)
        key = (job_id, output_format)
        with self._lock:
            current = self._states.get(key)
            if current and current.state == "preparing":
                return ArchiveState(**vars(current))
            if archive.is_file() and is_zipfile(archive):
                ready = ArchiveState(
                    state="ready",
                    completed_files=total_files,
                    total_files=total_files,
                    size_bytes=archive.stat().st_size,
                )
                self._states[key] = ready
                return ArchiveState(**vars(ready))
            if current and current.state == "failed":
                return ArchiveState(**vars(current))
            return ArchiveState(total_files=total_files)

    def prepare(self, job_id: str, output_format: str, files: list[Path]) -> ArchiveState:
        current = self.status(job_id, output_format, len(files))
        if current.state in {"preparing", "ready"}:
            return current
        state = ArchiveState(state="preparing", total_files=len(files))
        key = (job_id, output_format)
        with self._lock:
            # Recheck under the lock so simultaneous requests only launch one thread.
            existing = self._states.get(key)
            if existing and existing.state == "preparing":
                return ArchiveState(**vars(existing))
            self._states[key] = state
        thread = threading.Thread(
            target=self._build,
            args=(job_id, output_format, files),
            name=f"audiobook-{output_format}-archive-{job_id[:8]}",
            daemon=True,
        )
        thread.start()
        return ArchiveState(**vars(state))

    def is_preparing(self, job_id: str) -> bool:
        with self._lock:
            return any(
                key[0] == job_id and state.state == "preparing"
                for key, state in self._states.items()
            )

    def _build(self, job_id: str, output_format: str, files: list[Path]) -> None:
        archive, temporary = self._paths(job_id, output_format)
        key = (job_id, output_format)
        try:
            archive.parent.mkdir(parents=True, exist_ok=True)
            temporary.unlink(missing_ok=True)
            if archive.exists() and not is_zipfile(archive):
                archive.unlink()
            compression = ZIP_STORED if output_format == "mp3" else ZIP_DEFLATED
            with ZipFile(temporary, "w", compression=compression) as bundle:
                for completed, path in enumerate(files, 1):
                    if not path.is_file():
                        raise FileNotFoundError(f"Chapter audio is missing: {path.name}")
                    export_path = path
                    if output_format == "mp3":
                        export_path = temporary.parent / f".{path.stem}.export.mp3"
                    try:
                        if output_format == "mp3":
                            subprocess.run(
                                [
                                    self.ffmpeg_command,
                                    "-y",
                                    "-loglevel",
                                    "error",
                                    "-i",
                                    str(path),
                                    "-codec:a",
                                    "libmp3lame",
                                    "-b:a",
                                    self.mp3_bitrate,
                                    str(export_path),
                                ],
                                check=True,
                                capture_output=True,
                            )
                        bundle.write(export_path, arcname=f"{path.stem}.{output_format}")
                    finally:
                        if output_format == "mp3":
                            export_path.unlink(missing_ok=True)
                    with self._lock:
                        self._states[key].completed_files = completed
                        self._states[key].size_bytes = temporary.stat().st_size
            # Opening the central directory catches incomplete or malformed output.
            with ZipFile(temporary) as bundle:
                if len(bundle.infolist()) != len(files):
                    raise BadZipFile("Archive does not contain every chapter")
            temporary.replace(archive)
            with self._lock:
                state = self._states[key]
                state.state = "ready"
                state.size_bytes = archive.stat().st_size
        except Exception as exc:
            temporary.unlink(missing_ok=True)
            with self._lock:
                self._states[key] = ArchiveState(
                    state="failed",
                    total_files=len(files),
                    error=f"{type(exc).__name__}: {exc}",
                )
