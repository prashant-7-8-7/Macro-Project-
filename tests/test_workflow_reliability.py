import json
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import Mock

import numpy as np
import pytest

from src.api import routes
from src.database.repository import DocumentRepository
from src.database.db import get_connection
from src.retrieval.engine import HybridSearchEngine
from src.ai import rag


def document(doc_id):
    return dict(doc_id=doc_id, title=doc_id, filename=f"{doc_id}.txt", file_type="txt",
                file_size=10, doc_hash=f"hash-{doc_id}", metadata={}, language="en")


def chunk(doc_id, index=0, content="energy solar renewable"):
    return dict(id=f"{doc_id}-{index}", document_id=doc_id, chunk_index=index,
                content=content, token_count=3, page_number=1,
                embedding=np.array([1, 0], dtype=np.float32).tobytes())


def test_document_chunks_and_fts_roll_back_together():
    repo = DocumentRepository()
    bad = chunk("broken", 1)
    bad["embedding"] = None
    with pytest.raises(sqlite3.IntegrityError):
        repo.insert_document_with_chunks(**document("broken"), chunks=[chunk("broken"), bad])
    assert repo.get_document("broken") is None
    assert repo.get_document_chunks("broken") == []
    assert repo.search_fts("energy") == []


def test_duplicate_does_not_add_chunks_and_delete_clears_cache_and_fts():
    repo = DocumentRepository()
    assert repo.insert_document_with_chunks(**document("one"), chunks=[chunk("one")])
    duplicate = document("two")
    duplicate["doc_hash"] = "hash-one"
    assert not repo.insert_document_with_chunks(**duplicate, chunks=[chunk("two")])
    repo.set_cached_note_section("one", 1, "standard", "en", {"heading": "test"})
    repo.delete_document("one")
    assert repo.get_all_documents() == []
    assert repo.search_fts("energy") == []
    assert repo.get_cached_note_section("one", 1, "standard", "en") is None


def test_scoped_keyword_search_does_not_lose_matches_to_other_documents(monkeypatch):
    repo = DocumentRepository()
    repo.insert_document_with_chunks(**document("crowded"), chunks=[chunk("crowded", i) for i in range(30)])
    repo.insert_document_with_chunks(**document("target"), chunks=[chunk("target")])
    monkeypatch.setattr("src.retrieval.engine.EmbeddingEngine", Mock(side_effect=AssertionError("Keyword mode must not load a model")))
    result = HybridSearchEngine().search("energy", mode="keyword", top_k=1, filters={"document_id": "target"})
    assert len(result) == 1
    assert result[0]["document_id"] == "target"
    assert result[0]["chunk_index"] == 0
    assert {c["document_id"] for c in repo.get_all_chunks_with_embeddings({"document_id": "target"})} == {"target"}


def test_upload_retrieve_answer_duplicate_and_delete_flow(client, monkeypatch):
    from src.ingestion.pipeline import IngestionPipeline
    embeddings = Mock(embed_texts=lambda texts: np.array([[1, 0] for _ in texts], dtype=np.float32))
    monkeypatch.setattr(IngestionPipeline, "embedding_engine", property(lambda self: embeddings))
    monkeypatch.setattr(rag, "call_llm", lambda prompt: "Solar panels convert sunlight into electricity. [Source 1]")
    upload = client.post("/api/upload", files={"file": ("solar.txt", b"Solar panels convert sunlight into electricity. Renewable energy reduces pollution.")})
    assert upload.status_code == 200
    doc_id = upload.json()["document_id"]
    content = client.get(f"/api/documents/{doc_id}/content").json()
    assert content["document"]["filename"] == "solar.txt"
    assert len(content["chunks"]) == 1
    answer = client.post("/api/qa", json={"query": "solar", "mode": "keyword", "document_id": doc_id})
    assert answer.status_code == 200
    citation = answer.json()["citations"][0]
    assert citation["document_id"] == doc_id
    assert citation["chunk_index"] == 0
    duplicate = client.post("/api/upload", files={"file": ("copy.txt", b"Solar panels convert sunlight into electricity. Renewable energy reduces pollution.")})
    assert duplicate.json()["document_id"] == doc_id
    assert duplicate.json()["reason"] == "duplicate"
    assert len(client.get("/api/documents").json()["documents"]) == 1
    assert client.delete(f"/api/documents/{doc_id}").status_code == 200
    assert client.post("/api/search", json={"query": "solar", "mode": "keyword"}).json()["results"] == []


@pytest.mark.parametrize("payload", [
    {"query": "   "}, {"query": "x", "top_k": 0}, {"query": "x", "top_k": 51},
    {"query": "x", "mode": "invalid"}, {"query": "x", "filters": {"sql": "DROP TABLE documents"}},
])
def test_search_rejects_invalid_inputs(client, payload):
    assert client.post("/api/search", json=payload).status_code == 422


@pytest.mark.parametrize("filename,content,status", [
    ("notes.exe", b"data", 415), ("notes.txt", b"", 400), ("notes.txt", b"12345", 413),
])
def test_invalid_uploads_are_rejected_without_processing(client, monkeypatch, tmp_path, filename, content, status):
    pipeline = Mock()
    routes.app.dependency_overrides[routes.get_pipeline] = lambda: pipeline
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    monkeypatch.setattr(routes, "UPLOAD_DIR", upload_dir)
    monkeypatch.setattr(routes, "MAX_UPLOAD_BYTES", 4)
    assert client.post("/api/upload", files={"file": (filename, content)}).status_code == status
    pipeline.process_file.assert_not_called()
    assert list(upload_dir.iterdir()) == []


def test_upload_paths_are_isolated_and_removed_on_success_or_failure(client, monkeypatch, tmp_path):
    paths = []
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    def process(path):
        path = Path(path)
        assert path.is_relative_to(upload_dir)
        assert path.name == "notes.txt"
        assert path.read_bytes() == b"hello"
        paths.append(path)
        return {"status": "success", "document_id": "doc"}
    pipeline = Mock()
    pipeline.process_file.side_effect = process
    routes.app.dependency_overrides[routes.get_pipeline] = lambda: pipeline
    monkeypatch.setattr(routes, "UPLOAD_DIR", upload_dir)
    for filename in ("../../notes.txt", "C:\\uploads\\notes.txt"):
        assert client.post("/api/upload", files={"file": (filename, b"hello")}).status_code == 200
    assert paths[0] != paths[1]
    assert list(upload_dir.iterdir()) == []
    pipeline.process_file.side_effect = RuntimeError("invalid document")
    assert client.post("/api/upload", files={"file": ("notes.txt", b"hello")}).status_code == 422
    assert list(upload_dir.iterdir()) == []


def test_missing_documents_keep_404_status(client):
    assert client.post("/api/documents/missing/summarize").status_code == 404
    assert client.delete("/api/documents/missing").status_code == 404


def test_health_responds_while_an_answer_is_generating(client, monkeypatch):
    started, release = threading.Event(), threading.Event()
    def slow_answer(*args):
        started.set()
        assert release.wait(5)
        return {"answer": "done", "citations": []}
    routes.app.dependency_overrides[routes.get_engine] = lambda: Mock(search=Mock(return_value=[]))
    monkeypatch.setattr(routes, "synthesize_answer", slow_answer)
    with ThreadPoolExecutor(max_workers=2) as pool:
        answer = pool.submit(client.post, "/api/qa", json={"query": "test"})
        try:
            assert started.wait(3)
            health = pool.submit(client.get, "/api/health")
            assert health.result(timeout=2).json() == {"status": "ok"}
        finally:
            release.set()
        assert answer.result(timeout=3).status_code == 200
