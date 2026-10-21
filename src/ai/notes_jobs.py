import logging
import threading
import time
import uuid
import json
import hashlib
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)

class NotesQueueFull(RuntimeError):
    pass


class NotesJobManager:
    """
    Manages asynchronous background jobs for study notes generation.
    Enables non-blocking HTTP requests, polling with real-time progress,
    and graceful error/rate-limit recovery for large documents.
    """
    _instance = None
    _lock = threading.Lock()

    def __init__(self, max_concurrent: int = 2, max_pending: int = 8):
        self._jobs: Dict[str, Dict[str, Any]] = {}
        self._jobs_lock = threading.Lock()
        self._active_requests = {}
        self._worker_slots = threading.BoundedSemaphore(max_concurrent)
        self._max_pending = max_pending

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
        retry_fingerprint = hashlib.sha256(json.dumps(existing_notes or {}, sort_keys=True).encode()).hexdigest() if is_retry else ""
        request_key = (document_id, detail_level, notes_language or "original", doc_lang,
                       is_retry, tuple(sorted(set(retry_section_indices or []))), retry_fingerprint)
        with self._jobs_lock:
            previous_id = self._active_requests.get(request_key)
            if previous_id and self._jobs.get(previous_id, {}).get("status") in {"pending", "running"}:
                return previous_id
            # Keep completed jobs available for polling, while bounding retained results.
            terminal = sorted((job for job in self._jobs.values() if job["status"] in {"completed", "failed"}),
                              key=lambda job: job["updated_at"])
            for old in terminal:
                if time.time() - old["updated_at"] > 3600 or len(self._jobs) >= 100:
                    del self._jobs[old["job_id"]]
            if sum(job["status"] in {"pending", "running"} for job in self._jobs.values()) >= self._max_pending:
                raise NotesQueueFull("Notes generation is busy. Wait for an existing job to finish, then retry.")
            self._active_requests[request_key] = job_id
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
            target=self._run_limited_worker,
            args=(
                request_key,
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
        try:
            worker_thread.start()
        except Exception:
            with self._jobs_lock:
                self._active_requests.pop(request_key, None)
                del self._jobs[job_id]
            raise
        return job_id

    def _run_limited_worker(self, request_key, job_id, *args):
        try:
            with self._worker_slots:
                self._run_job_worker(job_id, *args)
        finally:
            with self._jobs_lock:
                if self._active_requests.get(request_key) == job_id:
                    self._active_requests.pop(request_key, None)

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
                if repo is not None and notes_res.get('notes'):
                    from src.database.study import StudyRepository
                    notes_res['version_id'] = StudyRepository().save_notes(document_id, notes_res['notes'], 'Generated study notes')
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
