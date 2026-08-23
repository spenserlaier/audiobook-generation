import queue
import threading

from .audio import write_mock_wav
from .config import Settings
from .crawler import CrawlCancelled, crawl
from .models import Chapter, JobStatus, SynthesisMode, VoiceStatus
from .store import JobStore
from .tts import QwenSynthesizer


class Pipeline:
    def __init__(self, settings: Settings, store: JobStore):
        self.settings = settings
        self.store = store
        self.tts = QwenSynthesizer(settings)

    def run(self, job_id: str, cancel_event: threading.Event | None = None) -> None:
        cancel_event = cancel_event or threading.Event()
        job = self.store.get(job_id)
        job_dir = self.settings.data_dir / "jobs" / job.id
        try:
            if cancel_event.is_set():
                raise CrawlCancelled("Job cancelled")
            self.store.update(
                job.id, status=JobStatus.CRAWLING, stage="Crawling novel", progress=0.02, error=None
            )
            if self.settings.mock_pipeline:
                total = job.chapter_limit or 3
                chapters = [
                    Chapter(
                        index=index,
                        title=f"Chapter {index}",
                        text=(f"This is mock chapter {index}. " * 20).strip(),
                    )
                    for index in range(1, total + 1)
                ]
            else:
                def report_crawl_progress(downloaded: int, total: int) -> None:
                    if cancel_event.is_set():
                        return
                    if total:
                        ratio = min(downloaded / total, 1.0)
                        stage = f"Crawling novel · {downloaded}/{total} chapters"
                    else:
                        ratio = 0
                        stage = f"Crawling novel · {downloaded} chapters"
                    self.store.update(job.id, stage=stage, progress=0.02 + 0.07 * ratio)

                chapters = crawl(
                    self.settings.crawler_command,
                    job.novel_url,
                    self.settings.data_dir / "crawler-state",
                    job.chapter_limit,
                    cancel_event,
                    report_crawl_progress,
                )
            if cancel_event.is_set():
                raise CrawlCancelled("Job cancelled")
            self.store.replace_chapters(job.id, chapters)
            title = job.title or "Audiobook"
            self.store.update(
                job.id,
                title=title,
                status=JobStatus.SYNTHESIZING,
                stage=f"Synthesizing 0/{len(chapters)} chapters",
                progress=0.1,
                chapters_total=len(chapters),
                chapters_completed=0,
                output_dir=str(job_dir / "audio"),
            )
            clone_prompt = None
            if job.synthesis_mode == SynthesisMode.DESIGNED_CLONE:
                if job.voice_id:
                    voice = self.store.get_voice(job.voice_id)
                    if voice.status != VoiceStatus.READY:
                        raise RuntimeError(f"Selected voice is not ready (status: {voice.status})")
                    reference_audio = (
                        self.settings.data_dir / "voices" / voice.id / "preview.wav"
                    )
                    reference_text = voice.reference_text
                    self.store.update(
                        job.id,
                        voice_preview_url=voice.preview_url,
                        stage=f"Using narrative voice: {voice.name}",
                    )
                else:
                    reference_audio = job_dir / "voice-reference.wav"
                    reference_text = job.reference_text
                    self.store.update(job.id, stage="Designing narrative voice")
                    if self.settings.mock_pipeline:
                        write_mock_wav(reference_audio, job.reference_text)
                    else:
                        self.tts.design_voice(
                            job.reference_text,
                            job.voice_description,
                            job.language,
                            reference_audio,
                        )
                    self.store.update(
                        job.id,
                        voice_preview_url=f"/api/jobs/{job.id}/voice-preview",
                        stage="Narrative voice ready",
                    )
                if cancel_event.is_set():
                    raise CrawlCancelled("Job cancelled")
                if not self.settings.mock_pipeline:
                    # Loading Base releases VoiceDesign and its CUDA allocation first.
                    clone_prompt = self.tts.create_clone_prompt(reference_audio, reference_text)
                if cancel_event.is_set():
                    raise CrawlCancelled("Job cancelled")
            for completed, chapter in enumerate(chapters, 1):
                if cancel_event.is_set():
                    raise CrawlCancelled("Job cancelled")
                output = job_dir / "audio" / f"chapter-{chapter.index:04d}.wav"
                self.store.update_chapter(job.id, chapter.index, status="synthesizing", error=None)
                if self.settings.mock_pipeline:
                    write_mock_wav(output, chapter.text)
                elif job.synthesis_mode == SynthesisMode.DESIGNED_CLONE:
                    self.tts.synthesize_clone(chapter.text, output, job.language, clone_prompt)
                else:
                    self.tts.synthesize_custom(
                        chapter.text, output, job.language, job.speaker, job.voice_instruction
                    )
                audio_url = f"/api/jobs/{job.id}/chapters/{chapter.index}/audio"
                self.store.update_chapter(
                    job.id, chapter.index, status="completed", audio_url=audio_url
                )
                self.store.update(
                    job.id,
                    chapters_completed=completed,
                    progress=0.1 + 0.9 * completed / len(chapters),
                    stage=f"Synthesized {completed}/{len(chapters)} chapters",
                )
            self.store.update(job.id, status=JobStatus.COMPLETED, stage="Complete", progress=1.0)
        except CrawlCancelled:
            self.store.update(
                job.id,
                status=JobStatus.CANCELLED,
                stage="Cancelled",
                error=None,
            )
        except Exception as exc:
            self.store.update(
                job.id,
                status=JobStatus.FAILED,
                stage="Failed",
                error=f"{type(exc).__name__}: {exc}",
            )
        finally:
            if self.settings.tts_release_after_job:
                self.tts.release()

    def generate_voice(self, voice_id: str) -> None:
        voice = self.store.get_voice(voice_id)
        output = self.settings.data_dir / "voices" / voice.id / "preview.wav"
        try:
            self.store.update_voice(
                voice.id, status=VoiceStatus.GENERATING, error=None
            )
            if self.settings.mock_pipeline:
                write_mock_wav(output, voice.reference_text)
            else:
                self.tts.design_voice(
                    voice.reference_text, voice.description, voice.language, output
                )
            self.store.update_voice(
                voice.id,
                status=VoiceStatus.READY,
                preview_url=f"/api/voices/{voice.id}/preview",
            )
        except Exception as exc:
            self.store.update_voice(
                voice.id,
                status=VoiceStatus.FAILED,
                error=f"{type(exc).__name__}: {exc}",
            )
        finally:
            if self.settings.tts_release_after_job:
                self.tts.release()


class WorkerPool:
    def __init__(self, pipeline: Pipeline, count: int = 1):
        self.pipeline = pipeline
        self.count = count
        self.queue: queue.Queue[tuple[str, str] | None] = queue.Queue()
        self.threads: list[threading.Thread] = []
        self._lock = threading.Lock()
        self._cancelled: set[str] = set()
        self._active: dict[str, threading.Event] = {}

    def start(self) -> None:
        for index in range(self.count):
            thread = threading.Thread(
                target=self._work, name=f"audiobook-worker-{index}", daemon=True
            )
            thread.start()
            self.threads.append(thread)

    def submit(self, job_id: str) -> None:
        self.queue.put(("job", job_id))

    def submit_voice(self, voice_id: str) -> None:
        self.queue.put(("voice", voice_id))

    def cancel(self, job_id: str) -> None:
        with self._lock:
            self._cancelled.add(job_id)
            event = self._active.get(job_id)
            if event:
                event.set()

    def _work(self) -> None:
        while True:
            task = self.queue.get()
            try:
                if task is None:
                    return
                kind, item_id = task
                if kind == "voice":
                    self.pipeline.generate_voice(item_id)
                else:
                    with self._lock:
                        if item_id in self._cancelled:
                            self._cancelled.discard(item_id)
                            continue
                        cancel_event = threading.Event()
                        self._active[item_id] = cancel_event
                    try:
                        self.pipeline.run(item_id, cancel_event)
                    finally:
                        with self._lock:
                            self._active.pop(item_id, None)
                            self._cancelled.discard(item_id)
            finally:
                self.queue.task_done()

    def stop(self) -> None:
        for _ in self.threads:
            self.queue.put(None)
        for thread in self.threads:
            thread.join(timeout=5)
        self.threads.clear()
