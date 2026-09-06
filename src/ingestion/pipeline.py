import os
import uuid
import hashlib
import logging
from pathlib import Path

from src.ingestion.parsers import DocumentParser
from src.ingestion.chunker import TextChunker
from src.ai.embeddings import EmbeddingEngine
from src.ai.vector_math import serialize_embedding
from src.database.repository import DocumentRepository

logger = logging.getLogger(__name__)

class IngestionPipeline:
    def __init__(self):
        self.repo = DocumentRepository()
        self.embedding_engine = EmbeddingEngine()
        
    def _compute_hash(self, file_path: str) -> str:
        hasher = hashlib.sha256()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hasher.update(chunk)
        return hasher.hexdigest()

    def process_file(self, file_path: str, metadata: dict = None) -> dict:
        """
        End-to-end ingestion of a document.
        Returns a summary of the ingestion process.
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
            
        file_size = path.stat().st_size
        doc_hash = self._compute_hash(file_path)
        
        # Deduplication check
        existing_doc = self.repo.get_document_by_hash(doc_hash)
        if existing_doc:
            logger.info(f"Document already exists: {path.name}")
            return {"status": "skipped", "reason": "duplicate", "document_id": existing_doc['id']}
            
        doc_id = str(uuid.uuid4())
        file_type = path.suffix.lower().lstrip('.')
        title = metadata.get("title", path.stem) if metadata else path.stem
        
        # 1. Parse Document
        logger.info(f"Parsing document: {path.name}")
        pages = DocumentParser.parse(str(path))
        
        # 2. Chunking
        logger.info(f"Chunking document...")
        chunks = TextChunker.chunk_pages(pages)
        
        if not chunks:
            logger.warning(f"No text extracted from {path.name}")
            return {"status": "failed", "reason": "no_text_extracted"}
            
        # 3. Embedding
        logger.info(f"Generating embeddings for {len(chunks)} chunks...")
        texts_to_embed = [c['content'] for c in chunks]
        embeddings_matrix = self.embedding_engine.embed_texts(texts_to_embed)
        
        # 4. Prepare for DB
        db_chunks = []
        for i, chunk in enumerate(chunks):
            chunk_id = str(uuid.uuid4())
            emb_blob = serialize_embedding(embeddings_matrix[i])
            db_chunks.append({
                "id": chunk_id,
                "document_id": doc_id,
                "chunk_index": chunk['chunk_index'],
                "content": chunk['content'],
                "token_count": chunk['token_count'],
                "page_number": chunk['page_number'],
                "embedding": emb_blob
            })
            
        # 5. Insert to DB Transactionally
        logger.info("Inserting into Relational SQL Database...")
        success = self.repo.insert_document(
            doc_id=doc_id,
            title=title,
            filename=path.name,
            file_type=file_type,
            file_size=file_size,
            doc_hash=doc_hash,
            metadata=metadata or {}
        )
        
        if success:
            self.repo.insert_chunks(db_chunks)
            logger.info(f"Successfully ingested {path.name} ({len(chunks)} chunks).")
            return {"status": "success", "document_id": doc_id, "chunks_count": len(chunks)}
        else:
            return {"status": "failed", "reason": "db_insert_error"}
