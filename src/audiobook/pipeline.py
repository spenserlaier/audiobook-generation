import queue
import threading

from .audio import write_mock_wav
from .config import Settings
from .crawler import crawl
from .models import Chapter, JobStatus, SynthesisMode
from .store import JobStore
from .tts import QwenSynthesizer


class Pipeline:
    def __init__(self, settings: Settings, store: JobStore):
        self.settings = settings
        self.store = store
        self.tts = QwenSynthesizer(settings)

    def run(self, job_id: str) -> None:
        job = self.store.get(job_id)
        job_dir = self.settings.data_dir / "jobs" / job.id
        try:
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
                chapters = crawl(
                    self.settings.crawler_command,
                    job.novel_url,
                    self.settings.data_dir / "crawler-state",
                    job.chapter_limit,
                )
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
                reference_audio = job_dir / "voice-reference.wav"
                self.store.update(
                    job.id,
                    stage="Designing narrative voice",
                )
                if self.settings.mock_pipeline:
                    write_mock_wav(reference_audio, job.reference_text)
                else:
                    self.tts.design_voice(
                        job.reference_text,
                        job.voice_description,
                        job.language,
                        reference_audio,
                    )
                    # Loading Base releases VoiceDesign and its CUDA allocation first.
                    clone_prompt = self.tts.create_clone_prompt(reference_audio, job.reference_text)
                self.store.update(
                    job.id,
                    voice_preview_url=f"/api/jobs/{job.id}/voice-preview",
                    stage="Narrative voice ready",
                )
            for completed, chapter in enumerate(chapters, 1):
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
        except Exception as exc:
            self.store.update(
                job.id,
                status=JobStatus.FAILED,
                stage="Failed",
                error=f"{type(exc).__name__}: {exc}",
            )


class WorkerPool:
    def __init__(self, pipeline: Pipeline, count: int = 1):
        self.pipeline = pipeline
        self.count = count
        self.queue: queue.Queue[str | None] = queue.Queue()
        self.threads: list[threading.Thread] = []

    def start(self) -> None:
        for index in range(self.count):
            thread = threading.Thread(
                target=self._work, name=f"audiobook-worker-{index}", daemon=True
            )
            thread.start()
            self.threads.append(thread)

    def submit(self, job_id: str) -> None:
        self.queue.put(job_id)

    def _work(self) -> None:
        while True:
            job_id = self.queue.get()
            try:
                if job_id is None:
                    return
                self.pipeline.run(job_id)
            finally:
                self.queue.task_done()

    def stop(self) -> None:
        for _ in self.threads:
            self.queue.put(None)
        for thread in self.threads:
            thread.join(timeout=5)
        self.threads.clear()
