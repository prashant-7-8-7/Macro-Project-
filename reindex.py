import time
import sys
import logging
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.config import EMBEDDING_MODEL_NAME
from src.database.db import init_db, set_system_metadata, get_system_metadata
from src.database.repository import DocumentRepository
from src.ai.embeddings import EmbeddingEngine
from src.ai.vector_math import serialize_embedding

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("reindex")


def reindex_all_documents(batch_size: int = 64) -> int:
    """
    Re-embeds all existing document chunks using the active multilingual embedding model.
    Updates the embedding BLOBs in SQLite and records the model name in system metadata.
    """
    print("=" * 60)
    print("AI Document Intelligence — Multilingual Re-indexing")
    print(f"Target Model: {EMBEDDING_MODEL_NAME}")
    print("=" * 60)

    start_time = time.time()
    init_db()

    previous_model = get_system_metadata("embedding_model")
    if previous_model:
        print(f"Previous Model: {previous_model}")

    repo = DocumentRepository()
    engine = EmbeddingEngine()

    chunks = repo.get_all_chunks_with_embeddings()
    total_chunks = len(chunks)

    if total_chunks == 0:
        print("No document chunks found in database to re-index.")
        set_system_metadata("embedding_model", EMBEDDING_MODEL_NAME)
        return 0

    print(f"Found {total_chunks} chunks to re-index. Starting batch embedding...")

    updates = []
    for i in range(0, total_chunks, batch_size):
        batch = chunks[i:i + batch_size]
        texts = [c["content"] for c in batch]
        embeddings = engine.embed_texts(texts)

        for j, emb in enumerate(embeddings):
            chunk_id = batch[j]["id"]
            blob = serialize_embedding(emb)
            updates.append((blob, chunk_id))

        pct = min(100.0, ((i + len(batch)) / total_chunks) * 100.0)
        print(f"  Processed {min(i + len(batch), total_chunks)}/{total_chunks} chunks ({pct:.1f}%)...")

    # Commit updates to database
    print("Writing updated embeddings to database...")
    repo.update_chunk_embeddings(updates)
    set_system_metadata("embedding_model", EMBEDDING_MODEL_NAME)

    elapsed = time.time() - start_time
    print("=" * 60)
    print(f"Re-indexing complete in {elapsed:.2f}s!")
    print(f"Total chunks re-embedded: {total_chunks}")
    print(f"Active model: {EMBEDDING_MODEL_NAME}")
    print("=" * 60)
    return total_chunks


if __name__ == "__main__":
    reindex_all_documents()
