import json
import sqlite3
import time
import unittest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from src.api.routes import app
from src.database.db import get_connection, migrate_db
from src.database.repository import DocumentRepository
from src.ai.notes import (
    generate_hierarchical_notes,
    retry_failed_sections,
    group_chunks_into_sections,
)
from src.ai.notes_jobs import NotesJobManager


class TestStep4BigDocsCache(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.repo = DocumentRepository()

    def setUp(self):
        # Ensure fresh DB migration
        conn = get_connection()
        migrate_db(conn)
        conn.close()

    def test_notes_section_cache_db_migration_and_methods(self):
        """Verify that notes_section_cache table exists and repository methods work."""
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='notes_section_cache';")
        self.assertIsNotNone(cursor.fetchone(), "notes_section_cache table should exist in DB")
        conn.close()

        doc_id = "test_doc_cache_001"
        try:
            self.repo.delete_document(doc_id)
        except Exception:
            pass
        self.repo.insert_document(
            doc_id=doc_id,
            title="Cache Test Doc 1",
            filename="cache_test_1.pdf",
            file_type="pdf",
            file_size=1024,
            doc_hash="hash_cache_test_001",
            metadata={},
            language="en"
        )

        sec_idx = 1
        detail = "standard"
        lang = "en"
        data = {
            "status": "success",
            "section_index": 1,
            "heading": "Cached Heading",
            "explanation": "Cached explanation text.",
            "bullets": ["Point A", "Point B"],
            "keyBox": {"title": "Key", "items": ["Item 1"]},
            "examples": ["Ex 1"],
            "tip": "Tip 1",
        }

        # 1. Set cached section
        self.repo.set_cached_note_section(doc_id, sec_idx, detail, lang, data)

        # 2. Retrieve cached section
        retrieved = self.repo.get_cached_note_section(doc_id, sec_idx, detail, lang)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.get("heading"), "Cached Heading")

        # 3. Retrieve all cached sections
        all_cached = self.repo.get_all_cached_note_sections(doc_id, detail, lang)
        self.assertIn(1, all_cached)
        self.assertEqual(all_cached[1]["heading"], "Cached Heading")

        # 4. Clean up
        self.repo.clear_note_sections_cache(doc_id)
        cleared = self.repo.get_cached_note_section(doc_id, sec_idx, detail, lang)
        self.assertIsNone(cleared)
        self.repo.delete_document(doc_id)

    @patch("src.ai.notes.call_llm")
    def test_generate_notes_uses_cached_sections(self, mock_llm):
        """Verify that pre-cached sections bypass the LLM and are directly loaded."""
        doc_id = "test_doc_cache_hit_002"
        try:
            self.repo.delete_document(doc_id)
        except Exception:
            pass
        self.repo.insert_document(
            doc_id=doc_id,
            title="Cache Test Doc 2",
            filename="cache_test_2.pdf",
            file_type="pdf",
            file_size=1024,
            doc_hash="hash_cache_test_002",
            metadata={},
            language="en"
        )

        chunks = [
            {"chunk_index": 0, "page_number": 1, "content": "Algorithms analyze computational efficiency and resource bounds. " * 80},
            {"chunk_index": 1, "page_number": 2, "content": "Divide and conquer algorithms partition problems into smaller instances. " * 80},
        ]

        # Seed section 1 in cache
        cached_sec_1 = {
            "status": "success",
            "section_index": 1,
            "heading": "Section 1 from Cache",
            "page_range": "p. 1",
            "explanation": "Loaded without LLM invocation.",
            "bullets": ["Cached concept"],
            "keyBox": {"title": "Cache Key", "items": ["Item"]},
            "examples": [],
            "tip": "Cached tip",
        }
        self.repo.set_cached_note_section(doc_id, 1, "standard", "en", cached_sec_1)

        # Mock LLM for section 2 only
        mock_llm.return_value = json.dumps({
            "heading": "Section 2 from LLM",
            "page_range": "p. 2",
            "explanation": "Processed by LLM.",
            "bullets": ["New concept"],
            "keyBox": {"title": "LLM Key", "items": ["Item"]},
            "examples": [],
            "tip": "LLM tip",
        })

        progress_steps = []
        def track_progress(completed, total, text):
            progress_steps.append((completed, total, text))

        res = generate_hierarchical_notes(
            chunks=chunks,
            doc_title="Caching Test",
            detail_level="standard",
            doc_lang="en",
            progress_callback=track_progress,
            document_id=doc_id,
            repo=self.repo,
            concurrency=2,
        )

        notes = res["notes"]
        self.assertIsNotNone(notes)
        sections = notes.get("sections", [])
        self.assertEqual(len(sections), 2)
        self.assertIn("from Cache", sections[0]["heading"])
        self.assertIn("from LLM", sections[1]["heading"])

        # Clean up
        self.repo.delete_document(doc_id)

    @patch("src.ai.notes.call_llm")
    def test_notes_background_job_lifecycle(self, mock_llm):
        """Test background job creation, asynchronous execution, and completion."""
        mock_llm.return_value = json.dumps({
            "heading": "Async Section",
            "explanation": "Computed in background thread.",
            "bullets": ["Background bullet 1"],
            "keyBox": {"title": "Async", "items": ["A"]},
            "examples": [],
            "tip": "Done",
        })

        chunks = [
            {"chunk_index": 0, "page_number": 1, "content": "Section content for background task test. " * 80}
        ]

        doc_id = "test_async_doc"
        try:
            self.repo.delete_document(doc_id)
        except Exception:
            pass
        self.repo.insert_document(
            doc_id=doc_id,
            title="Async Doc",
            filename="async_doc.pdf",
            file_type="pdf",
            file_size=1024,
            doc_hash="hash_async_doc_001",
            metadata={},
            language="en"
        )

        job_mgr = NotesJobManager.get_instance()
        job_id = job_mgr.create_job(
            document_id=doc_id,
            doc_title="Async Doc",
            chunks=chunks,
            detail_level="standard",
            notes_language="original",
            doc_lang="en",
            repo=self.repo,
        )

        self.assertIsNotNone(job_id)

        # Poll job until completion (with timeout)
        start_time = time.time()
        completed = False
        while time.time() - start_time < 10.0:
            job = job_mgr.get_job(job_id)
            self.assertIsNotNone(job)
            if job["status"] == "completed":
                completed = True
                self.assertIsNotNone(job["result"])
                self.assertEqual(job["progress_pct"], 100)
                break
            time.sleep(0.1)

        self.assertTrue(completed, "Background job should complete within 10 seconds")
        self.repo.delete_document(doc_id)

    @patch("src.ai.notes.generate_hierarchical_notes")
    def test_api_notes_background_mode(self, mock_gen):
        """Test API endpoint with background=true returns job_id and job can be queried."""
        mock_gen.return_value = {"notes": {"sections": []}}
        # Insert a dummy document in DB
        doc_id = "test_bg_endpoint_doc"
        try:
            self.repo.delete_document(doc_id)
        except Exception:
            pass

        self.repo.insert_document(
            doc_id=doc_id,
            title="BG Test Doc",
            filename="bg_test.pdf",
            file_type="pdf",
            file_size=1024,
            doc_hash="hash_bg_test_001",
            metadata={},
            language="en"
        )
        self.repo.insert_chunks([
            {
                "id": "chunk_bg_0",
                "document_id": doc_id,
                "chunk_index": 0,
                "content": "Test content for API background job endpoint test.",
                "token_count": 10,
                "page_number": 1,
                "embedding": b"\x00" * 1536
            }
        ])

        # Call endpoint with background=true
        res = self.client.post(f"/api/documents/{doc_id}/notes?background=true&detail_level=standard")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("job_id", data)
        self.assertEqual(data["status"], "running")

        job_id = data["job_id"]

        # Query job endpoint
        job_res = self.client.get(f"/api/documents/{doc_id}/notes/jobs/{job_id}")
        self.assertEqual(job_res.status_code, 200)
        job_data = job_res.json()
        self.assertIn(job_data["status"], ("pending", "running", "completed"))

        # Keep the mock and database alive until the worker has finished.
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            job_data = self.client.get(f"/api/documents/{doc_id}/notes/jobs/{job_id}").json()
            if job_data["status"] in ("completed", "failed"):
                break
            time.sleep(0.01)
        self.assertEqual(job_data["status"], "completed")
        mock_gen.assert_called_once()
        # Clean up
        self.repo.delete_document(doc_id)


if __name__ == "__main__":
    unittest.main()
