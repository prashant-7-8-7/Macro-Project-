import logging
import threading
import time
import uuid
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)


class NotesJobManager:
    """
    Manages asynchronous background jobs for study notes generation.
    Enables non-blocking HTTP requests, polling with real-time progress,
    and graceful error/rate-limit recovery for large documents.
    """
    _instance = None
    _lock = threading.Lock()

    def __init__(self):
        self._jobs: Dict[str, Dict[str, Any]] = {}
        self._jobs_lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> "NotesJobManager":
        with cls._lock:
            if cls._instance is None:
                cls._instance = NotesJobManager()
            return cls._instance

    def create_job(
        self,
        document_id: str,
        doc_title: str,
        chunks: List[Dict[str, Any]],
        detail_level: str = "standard",
        notes_language: str = "original",
        doc_lang: str = "en",
        repo: Any = None,
        is_retry: bool = False,
        retry_section_indices: Optional[List[int]] = None,
        existing_notes: Optional[Dict[str, Any]] = None,
    ) -> str:
        job_id = f"job_notes_{document_id}_{uuid.uuid4().hex[:8]}"
        with self._jobs_lock:
            self._jobs[job_id] = {
                "job_id": job_id,
                "document_id": document_id,
                "doc_title": doc_title,
                "status": "pending",
                "progress_pct": 5,
                "current_step": "Initializing notes generation...",
                "message": "Starting background worker...",
                "result": None,
                "error": None,
                "created_at": time.time(),
                "updated_at": time.time(),
            }

        worker_thread = threading.Thread(
            target=self._run_job_worker,
            args=(
                job_id,
                document_id,
                doc_title,
                chunks,
                detail_level,
                notes_language,
                doc_lang,
                repo,
                is_retry,
                retry_section_indices,
                existing_notes,
            ),
            daemon=True,
            name=f"NotesWorker-{job_id}",
        )
        worker_thread.start()
        return job_id

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        with self._jobs_lock:
            job = self._jobs.get(job_id)
            return dict(job) if job else None

    def update_job(self, job_id: str, **kwargs):
        with self._jobs_lock:
            if job_id in self._jobs:
                self._jobs[job_id].update(kwargs)
                self._jobs[job_id]["updated_at"] = time.time()

    def _run_job_worker(
        self,
        job_id: str,
        document_id: str,
        doc_title: str,
        chunks: List[Dict[str, Any]],
        detail_level: str,
        notes_language: str,
        doc_lang: str,
        repo: Any,
        is_retry: bool,
        retry_section_indices: Optional[List[int]],
        existing_notes: Optional[Dict[str, Any]],
    ):
        try:
            self.update_job(
                job_id,
                status="running",
                progress_pct=10,
                current_step="Preparing document sections...",
                message="Processing sections with concurrency control (2 workers)...",
            )

            def on_progress(completed: int, total: int, step_desc: str):
                pct = int(10 + (completed / max(1, total)) * 85)
                self.update_job(
                    job_id,
                    progress_pct=min(95, pct),
                    current_step=step_desc,
                    message=f"{completed} of {total} sections completed",
                )

            if is_retry and retry_section_indices and existing_notes:
                from src.ai.notes import retry_failed_sections
                updated_notes = retry_failed_sections(
                    chunks=chunks,
                    doc_title=doc_title,
                    target_section_indices=retry_section_indices,
                    existing_notes=existing_notes,
                    detail_level=detail_level,
                    doc_lang=doc_lang,
                    notes_language=notes_language,
                    repo=repo,
                    document_id=document_id,
                )
                self.update_job(
                    job_id,
                    status="completed",
                    progress_pct=100,
                    current_step="Retry completed successfully!",
                    message="All selected sections re-evaluated.",
                    result={
                        "document_id": document_id,
                        "filename": doc_title,
                        "notes": updated_notes,
                    },
                )
            else:
                from src.ai.notes import generate_hierarchical_notes
                notes_res = generate_hierarchical_notes(
                    chunks=chunks,
                    doc_title=doc_title,
                    detail_level=detail_level,
                    doc_lang=doc_lang,
                    notes_language=notes_language,
                    progress_callback=on_progress,
                    document_id=document_id,
                    repo=repo,
                    concurrency=2,
                )
                self.update_job(
                    job_id,
                    status="completed",
                    progress_pct=100,
                    current_step="Study notes ready!",
                    message="Notes successfully generated.",
                    result={
                        "document_id": document_id,
                        "filename": doc_title,
                        **notes_res,
                    },
                )

        except Exception as e:
            logger.exception("Background notes job failed: %s", e)
            self.update_job(
                job_id,
                status="failed",
                progress_pct=100,
                current_step="Notes generation failed",
                error=str(e),
                message=f"Error: {str(e)}",
            )
