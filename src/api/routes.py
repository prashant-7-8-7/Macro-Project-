from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.requests import Request
import os
import shutil
from pathlib import Path
from pydantic import BaseModel
from typing import List, Optional

from src.config import UPLOAD_DIR
from src.ingestion.pipeline import IngestionPipeline
from src.retrieval.engine import HybridSearchEngine
from src.ai.rag import synthesize_answer, summarize_document
from src.database.repository import DocumentRepository

app = FastAPI(title="AI Document Retrieval API")

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
async def upload_document(file: UploadFile = File(...), pipeline: IngestionPipeline = Depends(get_pipeline)):
    file_path = UPLOAD_DIR / file.filename
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        result = pipeline.process_file(str(file_path))
        return JSONResponse(status_code=200, content=result)
    except Exception as e:
        if file_path.exists():
            os.remove(file_path)
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
        if not chunks:
            raise HTTPException(status_code=404, detail="Document not found")
        
        # We can also fetch the document metadata here to get the title
        docs = repo.get_all_documents()
        doc_info = next((d for d in docs if d['id'] == doc_id), None)
        
        return {"document": doc_info, "chunks": chunks}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/documents/{doc_id}/summarize")
async def summarize_doc(doc_id: str, repo: DocumentRepository = Depends(get_repo)):
    try:
        chunks = repo.get_document_chunks_content(doc_id)
        if not chunks:
            raise HTTPException(status_code=404, detail="Document not found")
            
        docs = repo.get_all_documents()
        doc_info = next((d for d in docs if d['id'] == doc_id), None)
        title = doc_info['filename'] if doc_info else "Unknown Document"
        
        response = summarize_document(title, chunks)
        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
