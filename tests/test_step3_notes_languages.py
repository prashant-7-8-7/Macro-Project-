import json
import sys
import unittest
from unittest.mock import patch
from pathlib import Path
from fastapi.testclient import TestClient

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.ai.notes import (
    translate_section_notes,
    translate_full_notes,
    generate_hierarchical_notes,
    retry_failed_sections,
)
from src.api.routes import app


class TestStep3NotesLanguages(unittest.TestCase):

    def setUp(self):
        # Hindi synthetic chunks
        self.hindi_chunks = [
            {
                "chunk_index": 0,
                "page_number": 1,
                "language": "hi",
                "content": "मशीन लर्निंग (Machine Learning) कृत्रिम बुद्धिमत्ता की एक शाखा है। इसमें एल्गोरिदम डेटा से सीखते हैं।"
            },
            {
                "chunk_index": 1,
                "page_number": 2,
                "language": "hi",
                "content": "न्यूरल नेटवर्क (Neural Networks) मानव मस्तिष्क की कार्यप्रणाली पर आधारित होते हैं। ग्रेडिएंट डिसेंट भार को अनुकूलित करता है।"
            }
        ]

        # English synthetic chunks
        self.english_chunks = [
            {
                "chunk_index": 0,
                "page_number": 1,
                "language": "en",
                "content": "Distributed Systems and Consensus. Raft is a consensus algorithm designed to be easy to understand."
            }
        ]

    def test_translate_section_notes_keeps_structure_and_brackets(self):
        """Verify section translation keeps exact JSON structure and brackets for technical terms."""
        source_section = {
            "number": 1,
            "heading": "मशीन लर्निंग मूल बातें",
            "page_range": "p. 1",
            "color": "green",
            "layout": "split",
            "content": "मशीन लर्निंग डेटा से पैटर्न सीखता है।",
            "bullets": ["पर्यवेक्षित शिक्षण (Supervised Learning)", "अनियंत्रित शिक्षण (Unsupervised Learning)"],
            "keyBox": {"title": "महत्वपूर्ण सूत्र", "items": ["हानि फलन न्यूनतम करना"]},
            "tip": "हमेशा डेटा को सामान्य करें।"
        }

        def mock_llm_translate(prompt, **kwargs):
            return json.dumps({
                "heading": "Machine Learning Fundamentals",
                "explanation": "Machine learning learns patterns from data.",
                "bullets": [
                    "Supervised Learning [पर्यवेक्षित शिक्षण]",
                    "Unsupervised Learning [अनियंत्रित शिक्षण]"
                ],
                "keyBox": {
                    "title": "Important Formula",
                    "items": ["Minimize Loss Function [हानि फलन]"]
                },
                "tip": "Always normalize data."
            })

        with patch("src.ai.notes.call_llm", side_effect=mock_llm_translate):
            translated = translate_section_notes(
                section_dict=source_section,
                source_lang="hi",
                target_lang="en"
            )

        self.assertEqual(translated["number"], 1)
        self.assertEqual(translated["color"], "green")
        self.assertEqual(translated["layout"], "split")
        self.assertEqual(translated["language"], "en")
        self.assertEqual(translated["heading"], "Machine Learning Fundamentals")
        self.assertTrue(any("[" in b and "]" in b for b in translated["bullets"]))
        print("[OK] test_translate_section_notes_keeps_structure_and_brackets passed")

    def test_dual_notes_generation_for_hindi_doc(self):
        """Verify generating notes in 'both' mode produces identical sections in Hindi & English."""
        def mock_llm(prompt, **kwargs):
            # Check if this is a translation prompt
            if "Translate the following study notes section" in prompt:
                return json.dumps({
                    "heading": "Artificial Intelligence Concepts",
                    "explanation": "Neural networks simulate biological neuron behaviors.",
                    "bullets": [
                        "Backpropagation [बैकप्रॉपैगैशन] updates connection weights",
                        "Gradient Descent [ग्रेडिएंट डिसेंट] minimizes training error"
                    ],
                    "keyBox": {
                        "title": "Key Definition",
                        "items": ["Loss Function [हानि फलन]"]
                    },
                    "tip": "Avoid overfitting with regularization."
                })
            # Original extraction prompt in Hindi
            return json.dumps({
                "heading": "कृत्रिम बुद्धिमत्ता की अवधारणाएं",
                "explanation": "न्यूरल नेटवर्क जैविक न्यूरॉन व्यवहार का अनुकरण करते हैं।",
                "bullets": [
                    "बैकप्रॉपैगैशन (Backpropagation) भार को अपडेट करता है",
                    "ग्रेडिएंट डिसेंट (Gradient Descent) त्रुटि को कम करता है"
                ],
                "keyBox": {
                    "title": "मुख्य परिभाषा",
                    "items": ["हानि फलन (Loss Function)"]
                },
                "examples": ["डीप न्यूरल नेटवर्क"],
                "tip": "रेगुलराइजेशन से ओवरफिटिंग रोकें।"
            })

        with patch("src.ai.notes.call_llm", side_effect=mock_llm):
            res = generate_hierarchical_notes(
                chunks=self.hindi_chunks,
                doc_title="मशीन लर्निंग गाइड",
                detail_level="standard",
                doc_lang="hi",
                notes_language="both"
            )

        notes = res["notes"]
        self.assertEqual(notes["notes_mode"], "both")
        self.assertIn("dual_notes", notes)
        dual = notes["dual_notes"]

        self.assertIn("original", dual)
        self.assertIn("english", dual)

        orig_sections = dual["original"]["sections"]
        eng_sections = dual["english"]["sections"]

        # Exactly same number of sections in identical order
        self.assertEqual(len(orig_sections), len(eng_sections))
        self.assertGreater(len(orig_sections), 0)
        for i in range(len(orig_sections)):
            self.assertEqual(orig_sections[i]["number"], eng_sections[i]["number"])
            self.assertEqual(orig_sections[i]["color"], eng_sections[i]["color"])

        # English version preserves original technical terms in brackets
        eng_bullets = eng_sections[0]["bullets"]
        self.assertTrue(any("[" in b for b in eng_bullets))
        print("[OK] test_dual_notes_generation_for_hindi_doc passed")

    def test_english_doc_in_both_mode_stays_single_english(self):
        """When the document is already in English, 'both' mode keeps it clean English without redundant translation."""
        def mock_llm(prompt, **kwargs):
            return json.dumps({
                "heading": "Distributed Consensus",
                "explanation": "Consensus ensures state machines agree across nodes.",
                "bullets": ["Raft elects a leader", "Logs are replicated sequentially"],
                "keyBox": {"title": "Term", "items": ["Quorum"]},
                "examples": ["etcd", "Consul"],
                "tip": "Maintain majority node connectivity."
            })

        with patch("src.ai.notes.call_llm", side_effect=mock_llm):
            res = generate_hierarchical_notes(
                chunks=self.english_chunks,
                doc_title="Raft Paper",
                detail_level="standard",
                doc_lang="en",
                notes_language="both"
            )

        notes = res["notes"]
        self.assertEqual(notes["language"], "en")
        self.assertEqual(notes["notes_mode"], "single")
        self.assertNotIn("dual_notes", notes)
        print("[OK] test_english_doc_in_both_mode_stays_single_english passed")

    def test_api_notes_with_language_parameter(self):
        """Verify API /api/documents/{doc_id}/notes honors requested language parameter."""
        client = TestClient(app)

        from src.database.repository import DocumentRepository
        repo = DocumentRepository()
        docs = repo.get_all_documents()
        if not docs:
            print("[SKIP] test_api_notes_with_language_parameter: no documents in database.")
            return

        doc_id = docs[0]["id"]
        chunks = repo.get_document_chunks_content(doc_id)
        if not chunks:
            print("[SKIP] test_api_notes_with_language_parameter: document has no chunks.")
            return

        def mock_llm_api(prompt, **kwargs):
            return json.dumps({
                "heading": "Algorithm Design",
                "explanation": "Design techniques for polynomial time solutions.",
                "bullets": ["Divide and conquer divides the input problem"],
                "keyBox": {"title": "Complexity", "items": ["O(n log n)"]},
                "examples": ["Merge sort"],
                "tip": "Choose appropriate recurrence relation."
            })

        with patch("src.ai.notes.call_llm", side_effect=mock_llm_api):
            res = client.post(
                f"/api/documents/{doc_id}/notes",
                json={"detail_level": "brief", "language": "en"}
            )

        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("notes", data)
        self.assertEqual(data["notes"]["language"], "en")
        print("[OK] test_api_notes_with_language_parameter passed")


if __name__ == "__main__":
    unittest.main()
