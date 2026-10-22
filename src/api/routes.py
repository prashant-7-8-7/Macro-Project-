from src.quiz.generator import generate_questions
from src.quiz.validator import validate_questions
from src.quiz.schemas import QuizGenerateRequest, QuizResponse
from fastapi import FastAPI, UploadFile, File, HTTPException, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.requests import Request
import logging
import os
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict, StringConstraints
from typing import List, Optional, Literal, Annotated

logger = logging.getLogger(__name__)

from src.config import UPLOAD_DIR, MAX_UPLOAD_BYTES, ALLOWED_EXTENSIONS
from src.ingestion.pipeline import IngestionPipeline
from src.retrieval.engine import HybridSearchEngine
from src.ai.rag import synthesize_answer, summarize_document, generate_notes, retry_notes
from src.ai import budget
from src.ai.notes_jobs import NotesQueueFull
from src.database.repository import DocumentRepository

from src.database.db import init_db
from fastapi.middleware.cors import CORSMiddleware

from starlette.concurrency import run_in_threadpool

@asynccontextmanager
async def lifespan(app):
    await run_in_threadpool(on_startup)
    yield

app = FastAPI(title="AI Document Retrieval API", lifespan=lifespan)
from src.api.study import router as study_router
app.include_router(study_router)

# Enable CORS for external frontend hosting (e.g. Vercel)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in os.environ.get("CORS_ORIGINS", "*").split(",") if origin.strip()],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Page-Count", "X-Evidence-Highlighted"],
)

def on_startup():
    init_db()
    # Pre-warm embedding engine in background thread so cold-start doesn't stall requests
    import threading
    def warmup():
        try:
            from src.ai.embeddings import EmbeddingEngine
            EmbeddingEngine()
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Embedding warmup warning: {e}")
    if os.environ.get("EMBEDDING_WARMUP", "false").lower() == "true":
        threading.Thread(target=warmup, daemon=True).start()

# Setup Web Directories
BASE_DIR = Path(__file__).resolve().parent.parent
WEB_DIR = BASE_DIR / "web"
TEMPLATES_DIR = WEB_DIR / "templates"
STATIC_DIR = WEB_DIR / "static"

TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
STATIC_DIR.mkdir(parents=True, exist_ok=True)
(STATIC_DIR / "css").mkdir(exist_ok=True)
(STATIC_DIR / "js").mkdir(exist_ok=True)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Dependencies
def get_pipeline():
    return IngestionPipeline()

def get_engine():
    return HybridSearchEngine()

def get_repo():
    return DocumentRepository()

# --- Models ---
QueryText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]
SearchMode = Literal["keyword", "semantic", "hybrid"]

class SearchFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")
    document_id: Optional[str] = None
    filename: Optional[str] = None
    file_type: Optional[str] = None
    language: Optional[str] = None
    page_number: Optional[int] = Field(default=None, ge=1)

class SearchQuery(BaseModel):
    query: QueryText
    mode: SearchMode = "hybrid"
    top_k: int = Field(default=10, ge=1, le=50)
    filters: Optional[SearchFilters] = None

class QAQuery(BaseModel):
    query: QueryText
    mode: SearchMode = "hybrid"
    top_k: int = Field(default=5, ge=1, le=50)
    document_id: Optional[str] = None

# --- Web UI Route ---
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")

# --- API Routes ---
@app.get("/api/health")
def health():
    from src.database.db import get_connection
    from contextlib import closing
    with closing(get_connection()) as conn:
        conn.execute("SELECT COUNT(*) FROM documents").fetchone()
    return {"status": "ok"}

@app.post("/api/upload")
async def upload_document(file: UploadFile = File(...), pipeline: IngestionPipeline = Depends(get_pipeline)):
    try:
        # Never use a client-supplied path. Retain only its filename for display.
        filename = (file.filename or "").replace("\\", "/").rsplit("/", 1)[-1]
        if not filename or filename in {".", ".."} or len(filename) > 200 or any(ord(c) < 32 for c in filename):
            raise HTTPException(status_code=400, detail="Provide a valid filename (up to 200 characters).")
        if Path(filename).suffix.lower() not in ALLOWED_EXTENSIONS:
            raise HTTPException(status_code=415, detail="Supported files: PDF, TXT, MD, DOCX, CSV, JSON.")
        with tempfile.TemporaryDirectory(prefix="upload-", dir=UPLOAD_DIR) as temporary_dir:
            file_path = Path(temporary_dir) / filename
            size = 0
            with file_path.open("wb") as buffer:
                while content := await file.read(1024 * 1024):
                    size += len(content)
                    if size > MAX_UPLOAD_BYTES:
                        raise HTTPException(status_code=413, detail=f"File exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB upload limit.")
                    buffer.write(content)
            if size == 0:
                raise HTTPException(status_code=400, detail="Uploaded file is empty.")
            result = await run_in_threadpool(pipeline.process_file, str(file_path))
            if Path(filename).suffix.lower() == '.pdf' and result.get('document_id'):
                from src.ingestion.ocr import retain_original
                await run_in_threadpool(retain_original, result['document_id'], 'pdf', file_path)
            if result.get("status") == "failed":
                raise HTTPException(status_code=422, detail="No readable text could be extracted from this file.")
        return JSONResponse(status_code=200, content=result)
    except HTTPException:
        raise
    except (ValueError, RuntimeError) as exc:
        logger.warning("Document could not be processed: %s", exc)
        raise HTTPException(status_code=422, detail="This file could not be processed. Check its format and readable text.") from exc
    except Exception as exc:
        logger.exception("Error processing document during upload")
        raise HTTPException(status_code=500, detail="Document processing failed. Check the server logs.") from exc
    finally:
        await file.close()

@app.post("/api/search")
def search(query: SearchQuery, engine: HybridSearchEngine = Depends(get_engine)):
    try:
        results = engine.search(
            query=query.query, 
            mode=query.mode, 
            top_k=query.top_k, 
            filters=query.filters.model_dump(exclude_none=True) if query.filters else None
        )
        return {"query": query.query, "mode": query.mode, "results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/qa")
def ask_question(query: QAQuery, engine: HybridSearchEngine = Depends(get_engine)):
    try:
        filters = {}
        if query.document_id:
            filters['document_id'] = query.document_id
            
        # Retrieve context
        contexts = engine.search(
            query=query.query,
            mode=query.mode,
            top_k=query.top_k,
            filters=filters if filters else None
        )
        
        # Generate Answer
        response = synthesize_answer(query.query, contexts)
        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/documents")
def get_documents(repo: DocumentRepository = Depends(get_repo)):
    return {"documents": repo.get_all_documents()}

@app.delete("/api/documents/{doc_id}")
def delete_document(doc_id: str, repo: DocumentRepository = Depends(get_repo)):
    try:
        if not repo.get_document(doc_id):
            raise HTTPException(status_code=404, detail="Document not found")
        repo.delete_document(doc_id)
        return {"status": "success"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/documents/{doc_id}/content")
async def get_document_content(doc_id: str, repo: DocumentRepository = Depends(get_repo)):
    try:
        chunks = repo.get_document_chunks_content(doc_id)
        docs = repo.get_all_documents()
        doc_info = next((d for d in docs if d['id'] == doc_id), None)
        
        if not doc_info and not chunks:
            raise HTTPException(status_code=404, detail="Document not found")
        
        warning = None
        if doc_info and doc_info.get("metadata_json"):
            try:
                import json
                meta = json.loads(doc_info["metadata_json"])
                warning = meta.get("warning")
            except Exception:
                pass
        
        lang = doc_info.get("language", "en") if doc_info else "en"
        return {"document": doc_info, "chunks": chunks, "warning": warning, "language": lang}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
@app.post("/api/documents/{doc_id}/notes")
async def create_document_notes(
    doc_id: str,
    request: Request,
    repo: DocumentRepository = Depends(get_repo)
):
    try:
        detail_level = "standard"
        req_lang = None
        body = {}
        try:
            body = await request.json()
            if isinstance(body, dict):
                detail_level = body.get("detail_level", "standard")
                req_lang = body.get("language") or body.get("lang")
        except Exception:
            body = {}

        if not req_lang:
            req_lang = request.query_params.get("lang") or request.query_params.get("language")
        if request.query_params.get("detail_level"):
            detail_level = request.query_params.get("detail_level")

        chunks = repo.get_document_chunks_content(doc_id)

        if not chunks:
            raise HTTPException(
                status_code=404,
                detail="Document not found or contains no text."
            )

        docs = repo.get_all_documents()
        doc_info = next(
            (d for d in docs if d["id"] == doc_id),
            None
        )

        title = (
            doc_info["filename"]
            if doc_info
            else "Document Notes"
        )
        doc_detected_lang = doc_info.get("language", "en") if doc_info else "en"
        notes_lang = req_lang or "original"

        bg_param = request.query_params.get("background")
        is_background = (bg_param and bg_param.lower() in ("true", "1", "yes")) or (isinstance(body, dict) and body.get("background"))

        if is_background:
            from src.ai.notes_jobs import NotesJobManager
            job_mgr = NotesJobManager.get_instance()
            job_id = job_mgr.create_job(
                document_id=doc_id,
                doc_title=title,
                chunks=chunks,
                detail_level=detail_level or "standard",
                notes_language=notes_lang,
                doc_lang=doc_detected_lang,
                repo=repo,
            )
            return {
                "job_id": job_id,
                "document_id": doc_id,
                "status": "running",
                "progress_pct": 5,
                "current_step": "Starting notes generation...",
            }

        response = await run_in_threadpool(generate_notes,
            title,
            chunks,
            doc_lang=doc_detected_lang,
            detail_level=detail_level or "standard",
            notes_language=notes_lang,
            document_id=doc_id,
            repo=repo,
        )
        if response.get('notes'):
            from src.database.study import StudyRepository
            response['version_id'] = await run_in_threadpool(StudyRepository().save_notes, doc_id, response['notes'], 'Generated study notes')

        return {
            "document_id": doc_id,
            "filename": title,
            **response
        }

    except NotesQueueFull as exc:
        raise HTTPException(status_code=429, detail=str(exc), headers={"Retry-After": "15"}) from exc
    except HTTPException:
        raise

    except Exception as e:
        import logging
        logging.getLogger(__name__).exception(
            "Notes generation failed"
        )
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


@app.get("/api/documents/{doc_id}/notes/jobs/{job_id}")
async def get_notes_job_status(doc_id: str, job_id: str):
    from src.ai.notes_jobs import NotesJobManager
    job_mgr = NotesJobManager.get_instance()
    job = job_mgr.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Notes job not found.")
    return job


class RetryNotesRequest(BaseModel):
    section_indices: List[int]
    existing_notes: dict
    detail_level: Optional[str] = "standard"
    language: Optional[str] = None


@app.post("/api/documents/{doc_id}/notes/retry")
async def retry_document_notes_endpoint(
    doc_id: str,
    payload: RetryNotesRequest,
    request: Request,
    repo: DocumentRepository = Depends(get_repo)
):
    try:
        chunks = repo.get_document_chunks_content(doc_id)
        if not chunks:
            raise HTTPException(
                status_code=404,
                detail="Document not found or contains no text."
            )

        docs = repo.get_all_documents()
        doc_info = next(
            (d for d in docs if d["id"] == doc_id),
            None
        )

        title = (
            doc_info["filename"]
            if doc_info
            else "Document Notes"
        )
        doc_lang = payload.language or (doc_info.get("language", "en") if doc_info else "en")
        notes_lang = payload.language or payload.existing_notes.get("notes_mode")

        bg_param = request.query_params.get("background")
        is_background = bg_param and bg_param.lower() in ("true", "1", "yes")

        if is_background:
            from src.ai.notes_jobs import NotesJobManager
            job_mgr = NotesJobManager.get_instance()
            job_id = job_mgr.create_job(
                document_id=doc_id,
                doc_title=title,
                chunks=chunks,
                detail_level=payload.detail_level or "standard",
                notes_language=notes_lang,
                doc_lang=doc_lang,
                repo=repo,
                is_retry=True,
                retry_section_indices=payload.section_indices,
                existing_notes=payload.existing_notes,
            )
            return {
                "job_id": job_id,
                "document_id": doc_id,
                "status": "running",
                "progress_pct": 5,
                "current_step": "Starting retry for skipped sections...",
            }

        updated_notes = await run_in_threadpool(retry_notes,
            doc_title=title,
            chunks=chunks,
            target_section_indices=payload.section_indices,
            existing_notes=payload.existing_notes,
            detail_level=payload.detail_level or "standard",
            doc_lang=doc_lang,
            notes_language=notes_lang,
            repo=repo,
            document_id=doc_id,
        )

        return {
            "document_id": doc_id,
            "filename": title,
            "notes": updated_notes
        }

    except NotesQueueFull as exc:
        raise HTTPException(status_code=429, detail=str(exc), headers={"Retry-After": "15"}) from exc
    except HTTPException:
        raise

    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Notes retry failed")
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

@app.post("/api/documents/{doc_id}/summarize")
def summarize_doc(doc_id: str, repo: DocumentRepository = Depends(get_repo)):
    try:
        chunks = repo.get_document_chunks_content(doc_id)
        if not chunks:
            raise HTTPException(status_code=404, detail="Document not found")
            
        docs = repo.get_all_documents()
        doc_info = next((d for d in docs if d['id'] == doc_id), None)
        title = doc_info['filename'] if doc_info else "Unknown Document"
        doc_lang = doc_info.get("language", "en") if doc_info else "en"
        
        response = summarize_document(title, chunks, doc_lang=doc_lang)
        return response
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
@app.post("/api/quiz/generate", response_model=QuizResponse)
def generate_quiz(
    request: QuizGenerateRequest,
    repo: DocumentRepository = Depends(get_repo),
):
    budget.clear_issue()
    try:
        # Get chunks belonging ONLY to this document
        contexts = repo.get_document_chunks_content(
            request.document_id
        )

        if not contexts:
            raise HTTPException(
                status_code=404,
                detail="Document not found or contains no text."
            )

        if request.focus_weak_topics:
            from src.database.study import StudyRepository
            wrong = StudyRepository().progress(request.document_id)['wrong_questions']
            indexes = {str(q.get('source_chunk_id')) for q in wrong}
            focused = [chunk for chunk in contexts if str(chunk['chunk_index']) in indexes]
            if focused:
                contexts = focused
        logger.info(
            "[Quiz Route] Incoming quiz request: doc_id=%s, requested=%d, difficulty=%s, total_doc_chunks=%d",
            request.document_id,
            request.num_questions,
            request.difficulty,
            len(contexts),
        )

        # Generate candidate questions via batch generation
        questions = generate_questions(
            contexts=contexts,
            num_questions=request.num_questions,
            difficulty=request.difficulty,
        )
        if not questions and budget.last_issue_message():
            raise HTTPException(status_code=503, detail=budget.last_issue_message())

        # Independently validate generated questions
        verified, rejected = validate_questions(
            questions,
            contexts,
        )

        total_generated = len(questions)
        attempted_stems = [q.question for q in questions]

        # Retry loop: if verified count is below requested, make up to 3 retry attempts for only missing number
        retry_attempts = 0
        while len(verified) < request.num_questions and retry_attempts < 3 and not budget.last_issue_message():
            retry_attempts += 1
            missing_count = request.num_questions - len(verified)
            logger.info(
                "[Quiz Route Retry] Attempt %d/3: Generating %d missing questions (current verified=%d, requested=%d)",
                retry_attempts,
                missing_count,
                len(verified),
                request.num_questions,
            )

            retry_candidates = generate_questions(
                contexts=contexts,
                num_questions=missing_count,
                difficulty=request.difficulty,
                existing_questions=attempted_stems,
                batch_offset=retry_attempts,
            )
            if not retry_candidates:
                break

            total_generated += len(retry_candidates)
            attempted_stems.extend(q.question for q in retry_candidates)
            more_verified, more_rejected = validate_questions(
                retry_candidates,
                contexts,
            )

            seen_existing = {" ".join(q.question.lower().split()) for q in verified}
            newly_added = 0
            for mq in more_verified:
                norm_q = " ".join(mq.question.lower().split())
                if norm_q not in seen_existing:
                    seen_existing.add(norm_q)
                    verified.append(mq)
                    newly_added += 1

            rejected.extend(more_rejected)
            logger.info(
                "[Quiz Route Retry] Attempt %d added %d newly verified questions (total verified now: %d)",
                retry_attempts,
                newly_added,
                len(verified),
            )

            if newly_added == 0:
                break

        # Trim verified questions to requested count if extra were generated
        if len(verified) > request.num_questions:
            verified = verified[:request.num_questions]

        # Transparent message if document content was too small to reach requested count
        message = None
        if len(verified) < request.num_questions:
            message = f"Generated {len(verified)} verified questions of {request.num_questions} requested."
            if budget.last_issue_message():
                message += ' ' + budget.last_issue_message()
        else:
            message = f"{len(verified)} verified questions generated successfully."

        logger.info(
            "[Quiz Route] Final result for doc_id=%s: requested=%d, verified=%d, total_generated=%d, rejected=%d, message='%s'",
            request.document_id,
            request.num_questions,
            len(verified),
            total_generated,
            len(rejected),
            message,
        )

        from src.database.study import StudyRepository
        quiz_id = StudyRepository().save_quiz(request.document_id, [q.model_dump() for q in verified]) if verified else None
        return QuizResponse(
            quiz_id=quiz_id,
            document_id=request.document_id,
            questions=verified,
            generated_count=total_generated,
            verified_count=len(verified),
            rejected_count=len(rejected),
            message=message,
        )

    except HTTPException:
        raise

    except Exception as e:
        import logging
        logging.getLogger(__name__).exception(
            "Quiz generation failed"
        )
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )
