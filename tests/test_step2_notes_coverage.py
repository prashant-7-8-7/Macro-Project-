import sys
import unittest
from unittest.mock import patch
from pathlib import Path
from fastapi.testclient import TestClient

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.ai.notes import (
    group_chunks_into_sections,
    map_section_to_notes,
    generate_hierarchical_notes,
    retry_failed_sections,
)
from src.api.routes import app


class TestStep2NotesCoverage(unittest.TestCase):

    def setUp(self):
        # 12 chunks across 6 pages
        self.chunks = []
        chunk_idx = 0
        for page in range(1, 7):
            for sub in range(2):
                self.chunks.append({
                    "chunk_index": chunk_idx,
                    "page_number": page,
                    "content": f"Page {page} paragraph {sub}. " + ("Distributed systems, consistency, and fault tolerance concepts. " * 30)
                })
                chunk_idx += 1

    def test_coverage_tracking_all_succeed(self):
        """When all sections succeed, coverage indicates full coverage and no skipped pages."""
        # Mock call_llm to always succeed with valid JSON
        def mock_llm(prompt, **kwargs):
            return """
            {
                "heading": "Distributed System Architecture",
                "explanation": "Thorough discussion on network partitions and consensus algorithms.",
                "bullets": [
                    "Raft consensus ensures strong consistency across replicas.",
                    "Paxos handles asynchronous communication safely."
                ],
                "keyBox": {
                    "title": "CAP Theorem",
                    "items": ["Consistency, Availability, Partition tolerance"]
                },
                "examples": ["Raft in etcd"],
                "tip": "Always account for network partitions."
            }
            """

        with patch("src.ai.notes.call_llm", side_effect=mock_llm):
            result = generate_hierarchical_notes(
                chunks=self.chunks,
                doc_title="Distributed Systems Guide",
                detail_level="standard",
                doc_lang="en"
            )

        notes = result["notes"]
        self.assertIsNotNone(notes)
        coverage = notes["coverage"]
        self.assertEqual(len(coverage["failed_sections"]), 0)
        self.assertEqual(coverage["processed_sections"], coverage["total_sections"])
        self.assertIsNone(coverage["skipped_pages_text"])
        self.assertIn("Covered pages 1-6 of 6", coverage["coverage_text"])
        self.assertIn("sections", coverage["coverage_text"])
        print("[OK] test_coverage_tracking_all_succeed passed")

    def test_coverage_tracking_with_failed_section(self):
        """When a section fails after retries, it is recorded in failed_sections without silent skipping."""
        # Mock call_llm to fail ONLY on section 2 text
        def mock_llm(prompt, **kwargs):
            if "pp. 3-4" in prompt or "p. 3" in prompt or "p. 4" in prompt or "from pp. 3-4" in prompt:
                return None  # Simulate LLM failure (e.g. rate limit 429)
            return """
            {
                "heading": "Reliable Replication",
                "explanation": "Core consensus and replication primitives.",
                "bullets": ["State machine replication guarantees linearizability."],
                "keyBox": {"title": "Key Term", "items": ["Quorum consensus"]},
                "examples": ["ZooKeeper zab protocol"],
                "tip": "Maintain majority quorums."
            }
            """

        with patch("src.ai.notes.call_llm", side_effect=mock_llm):
            result = generate_hierarchical_notes(
                chunks=self.chunks,
                doc_title="Distributed Systems Guide",
                detail_level="standard",
                doc_lang="en"
            )

        notes = result["notes"]
        self.assertIsNotNone(notes)
        coverage = notes["coverage"]

        # Exactly 1 section failed
        self.assertEqual(len(coverage["failed_sections"]), 1)
        failed_sec = coverage["failed_sections"][0]
        self.assertIn("p", failed_sec["page_label"])
        self.assertIsNotNone(coverage["skipped_pages_text"])
        self.assertIn("Skipped pages:", coverage["skipped_pages_text"])
        self.assertIn("failed after retries", coverage["skipped_pages_text"])
        self.assertIn(f"Covered {coverage['processed_sections']} of {coverage['total_sections']} sections", coverage["coverage_text"])

        # The other sections still succeeded and are in notes["sections"]
        self.assertEqual(len(notes["sections"]), coverage["processed_sections"])
        print("[OK] test_coverage_tracking_with_failed_section passed")

    def test_retry_failed_sections_merges_in_order(self):
        """Retrying the failed section successfully merges it into existing_notes and clears skipped pages."""
        # 1. First run with section 2 failing
        def mock_llm_fail_sec2(prompt, **kwargs):
            if "pp. 3-4" in prompt or "p. 3" in prompt or "p. 4" in prompt or "from pp. 3-4" in prompt:
                return None
            return """
            {
                "heading": "Standard Section",
                "explanation": "Regular notes section.",
                "bullets": ["Point A", "Point B"],
                "keyBox": {"title": "Key", "items": ["Def"]},
                "examples": [],
                "tip": "Tip"
            }
            """

        with patch("src.ai.notes.call_llm", side_effect=mock_llm_fail_sec2):
            initial_result = generate_hierarchical_notes(
                chunks=self.chunks,
                doc_title="Distributed Systems Guide",
                detail_level="standard",
                doc_lang="en"
            )

        initial_notes = initial_result["notes"]
        failed_indices = [fs["section_index"] for fs in initial_notes["coverage"]["failed_sections"]]
        self.assertEqual(len(failed_indices), 1)
        failed_sec_idx = failed_indices[0]

        # 2. Now retry with LLM succeeding
        def mock_llm_succeed(prompt, **kwargs):
            return """
            {
                "heading": "Recovered Section",
                "explanation": "Recovered section explanation after retry.",
                "bullets": ["Recovered Point 1", "Recovered Point 2"],
                "keyBox": {"title": "Recovered Key", "items": ["Recovered Def"]},
                "examples": ["Case X"],
                "tip": "Recovered Tip"
            }
            """

        with patch("src.ai.notes.call_llm", side_effect=mock_llm_succeed):
            updated_notes = retry_failed_sections(
                chunks=self.chunks,
                doc_title="Distributed Systems Guide",
                target_section_indices=failed_indices,
                existing_notes=initial_notes,
                detail_level="standard",
                doc_lang="en"
            )

        # 3. Verify section was spliced in and sorted
        sec_numbers = [s["number"] for s in updated_notes["sections"]]
        self.assertEqual(sec_numbers, sorted(sec_numbers))
        self.assertIn(failed_sec_idx, sec_numbers)

        # Verify coverage is now 100%
        updated_cov = updated_notes["coverage"]
        self.assertEqual(len(updated_cov["failed_sections"]), 0)
        self.assertIsNone(updated_cov["skipped_pages_text"])
        self.assertIn("Covered pages 1-6 of 6", updated_cov["coverage_text"])
        print("[OK] test_retry_failed_sections_merges_in_order passed")

    def test_api_retry_notes_endpoint(self):
        """Test POST /api/documents/{doc_id}/notes/retry endpoint."""
        client = TestClient(app)

        # Get existing documents in repo to test with a real doc_id
        from src.database.repository import DocumentRepository
        repo = DocumentRepository()
        docs = repo.get_all_documents()
        if not docs:
            print("[SKIP] test_api_retry_notes_endpoint: no documents in database, skipping API call test.")
            return

        doc_id = docs[0]["id"]
        chunks = repo.get_document_chunks_content(doc_id)
        if not chunks:
            print("[SKIP] test_api_retry_notes_endpoint: document has no chunks.")
            return

        # Create dummy initial notes with a failed section
        existing_notes = {
            "title": "Test Doc",
            "subject": "Study Notes",
            "quote": "Quote",
            "detail_level": "standard",
            "sections": [
                {
                    "number": 1,
                    "heading": "Section 1",
                    "color": "green",
                    "layout": "full",
                    "content": "Content",
                    "bullets": ["Bullet 1"],
                    "keyBox": {"title": "Key", "items": ["Item"]},
                    "tip": "Tip"
                }
            ],
            "keyTakeaways": ["Takeaway 1"],
            "remember": ["Remember 1"],
            "coverage": {
                "total_sections": 2,
                "processed_sections": 1,
                "successful_section_indices": [1],
                "failed_sections": [
                    {
                        "section_index": 2,
                        "page_start": 2,
                        "page_end": 2,
                        "page_label": "p. 2",
                        "error": "Timeout"
                    }
                ],
                "min_page": 1,
                "max_page": 2,
                "coverage_text": "Covered 1 of 2 sections (pages 1-2)",
                "skipped_pages_text": "Skipped pages: p. 2 (1 section failed after retries)"
            }
        }

        def mock_llm_retry(prompt, **kwargs):
            return """
            {
                "heading": "Section 2 Recovered",
                "explanation": "Retried section content.",
                "bullets": ["Bullet A"],
                "keyBox": {"title": "Key", "items": ["Item"]},
                "examples": [],
                "tip": "Tip"
            }
            """

        with patch("src.ai.notes.call_llm", side_effect=mock_llm_retry):
            res = client.post(
                f"/api/documents/{doc_id}/notes/retry",
                json={
                    "section_indices": [2],
                    "existing_notes": existing_notes,
                    "detail_level": "standard"
                }
            )

        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("notes", data)
        self.assertEqual(data["document_id"], doc_id)
        cov = data["notes"]["coverage"]
        self.assertEqual(len(cov["failed_sections"]), 0)
        self.assertIsNone(cov["skipped_pages_text"])
        print("[OK] test_api_retry_notes_endpoint passed")


if __name__ == "__main__":
    unittest.main()
