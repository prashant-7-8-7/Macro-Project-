from src.quiz.generator import generate_questions
from src.quiz.validator import validate_questions
from src.quiz.schemas import QuizGenerateRequest, QuizResponse
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Depends, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.requests import Request
import logging
import os
import shutil
from pathlib import Path
from pydantic import BaseModel
from typing import List, Optional

logger = logging.getLogger(__name__)

from src.config import UPLOAD_DIR
from src.ingestion.pipeline import IngestionPipeline
from src.retrieval.engine import HybridSearchEngine
from src.ai.rag import synthesize_answer, summarize_document, generate_notes
from src.database.repository import DocumentRepository

from src.database.db import init_db
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="AI Document Retrieval API")

# Enable CORS for external frontend hosting (e.g. Vercel)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from starlette.concurrency import run_in_threadpool

@app.on_event("startup")
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
class SearchQuery(BaseModel):
    query: str
    mode: str = "hybrid" # keyword, semantic, hybrid
    top_k: int = 10
    filters: Optional[dict] = None

class QAQuery(BaseModel):
    query: str
    mode: str = "hybrid"
    top_k: int = 5
    document_id: Optional[str] = None

# --- Web UI Route ---
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")

# --- API Routes ---
@app.post("/api/upload")
async def upload_document(background_tasks: BackgroundTasks, file: UploadFile = File(...), pipeline: IngestionPipeline = Depends(get_pipeline)):
    file_path = UPLOAD_DIR / file.filename
    try:
        content = await file.read()
        if not content:
            raise ValueError("Uploaded file is empty.")
        with open(file_path, "wb") as buffer:
            buffer.write(content)
        result = await run_in_threadpool(pipeline.process_file, str(file_path))
        return JSONResponse(status_code=200, content=result)
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Error processing document during upload")
        if file_path.exists():
            try:
                os.remove(file_path)
            except Exception:
                pass
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/search")
async def search(query: SearchQuery, engine: HybridSearchEngine = Depends(get_engine)):
    try:
        results = engine.search(
            query=query.query, 
            mode=query.mode, 
            top_k=query.top_k, 
            filters=query.filters
        )
        return {"query": query.query, "mode": query.mode, "results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/qa")
async def ask_question(query: QAQuery, engine: HybridSearchEngine = Depends(get_engine)):
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
async def get_documents(repo: DocumentRepository = Depends(get_repo)):
    return {"documents": repo.get_all_documents()}

@app.delete("/api/documents/{doc_id}")
async def delete_document(doc_id: str, repo: DocumentRepository = Depends(get_repo)):
    try:
        repo.delete_document(doc_id)
        return {"status": "success"}
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
        doc_lang = doc_info.get("language", "en") if doc_info else "en"

        response = generate_notes(title, chunks, doc_lang=doc_lang)

        return {
            "document_id": doc_id,
            "filename": title,
            **response
        }

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

@app.post("/api/documents/{doc_id}/summarize")
async def summarize_doc(doc_id: str, repo: DocumentRepository = Depends(get_repo)):
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
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
@app.post("/api/quiz/generate", response_model=QuizResponse)
async def generate_quiz(
    request: QuizGenerateRequest,
    repo: DocumentRepository = Depends(get_repo),
):
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

        # Independently validate generated questions
        verified, rejected = validate_questions(
            questions,
            contexts,
        )

        total_generated = len(questions)

        # Retry loop: if verified count is below requested, make up to 3 retry attempts for only missing number
        retry_attempts = 0
        while len(verified) < request.num_questions and retry_attempts < 3:
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
            )
            if not retry_candidates:
                break

            total_generated += len(retry_candidates)
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
            message = f"Only {len(verified)} verified questions could be generated from this document (requested {request.num_questions})."
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

        return QuizResponse(
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