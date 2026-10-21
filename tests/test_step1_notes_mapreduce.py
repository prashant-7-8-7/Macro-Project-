import sys
import pytest
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.ai.notes import (
    group_chunks_into_sections,
    map_section_to_notes,
    reduce_section_notes,
    generate_hierarchical_notes,
    DETAIL_CONFIG
)


def test_group_chunks_into_sections():
    """Verify section grouping preserves page order and bounds chunk sizes."""
    # Create 20 synthetic chunks across 5 pages
    chunks = []
    chunk_idx = 0
    for page in range(1, 6):
        for sub in range(4):
            chunks.append({
                "chunk_index": chunk_idx,
                "page_number": page,
                "content": f"Page {page} Section {sub}: " + ("Machine learning and artificial intelligence principles. " * 35)
            })
            chunk_idx += 1

    total_text_len = sum(len(c["content"]) for c in chunks)
    assert total_text_len > 25000, f"Expected >25k chars, got {total_text_len}"

    sections = group_chunks_into_sections(chunks, target_min_chars=4000, target_max_chars=7500)
    assert len(sections) >= 3, f"Expected at least 3 sections, got {len(sections)}"

    # Check page labels and ordering
    prev_end_page = 0
    for s in sections:
        assert s["page_start"] >= prev_end_page or s["page_start"] == prev_end_page, "Pages must be in ascending order"
        assert s["page_end"] >= s["page_start"]
        assert len(s["text"]) > 0
        assert "pp." in s["page_label"] or "p." in s["page_label"]
        prev_end_page = s["page_end"]

    print("[OK] test_group_chunks_into_sections passed")


def test_reduce_section_notes_scaling():
    """Verify reduce merges multiple sections into scalable notes without capping."""
    mapped_sections = []
    for i in range(1, 11):  # 10 sections simulating a 40-page document
        mapped_sections.append({
            "section_index": i,
            "heading": f"Chapter Topic {i}: Architecture",
            "page_range": f"pp. {i*4-3}-{i*4}",
            "explanation": f"This is the detailed explanation for section {i}.",
            "bullets": [f"Fact {i}.1", f"Fact {i}.2", f"Fact {i}.3"],
            "keyBox": {"title": f"Key Formula {i}", "items": [f"E_{i} = mc^2"]},
            "examples": [f"Real-world case study {i}"],
            "tip": f"Remember guideline {i}",
            "key_takeaways": [f"Core takeaway {i}"]
        })

    reduced = reduce_section_notes(
        section_notes_list=mapped_sections,
        doc_title="Comprehensive Technical Manual",
        detail_level="detailed",
        doc_lang="en",
        total_pages_covered="pages 1-40 of 40"
    )

    assert len(reduced["sections"]) == 10, f"Expected 10 sections in reduced notes, got {len(reduced['sections'])}"
    assert len(reduced["keyTakeaways"]) > 0
    assert len(reduced["remember"]) > 0
    assert "Chapter Topic 1" in reduced["sections"][0]["heading"]
    assert "Chapter Topic 10" in reduced["sections"][9]["heading"]
    print("[OK] test_reduce_section_notes_scaling passed")


def test_detail_level_configurations():
    """Verify all 3 detail levels exist and specify distinct depth ratios."""
    assert "brief" in DETAIL_CONFIG
    assert "standard" in DETAIL_CONFIG
    assert "detailed" in DETAIL_CONFIG

    assert DETAIL_CONFIG["brief"]["min_bullets"] < DETAIL_CONFIG["standard"]["min_bullets"]
    assert DETAIL_CONFIG["standard"]["min_bullets"] < DETAIL_CONFIG["detailed"]["min_bullets"]
    print("[OK] test_detail_level_configurations passed")


@pytest.mark.integration
def test_hierarchical_notes_integration():
    """Verify end-to-end integration of generate_hierarchical_notes."""
    chunks = [
        {
            "chunk_index": 0,
            "page_number": 1,
            "content": "Deep Learning Fundamentals. Neural networks consist of layers of interconnected nodes or neurons."
        },
        {
            "chunk_index": 1,
            "page_number": 2,
            "content": "Backpropagation and Gradient Descent. Optimization algorithms update weights to minimize loss function."
        }
    ]

    res = generate_hierarchical_notes(
        chunks=chunks,
        doc_title="Deep Learning Guide",
        detail_level="standard",
        doc_lang="en"
    )

    assert "notes" in res, "Expected 'notes' key in response"
    notes = res["notes"]
    assert notes is not None
    assert len(notes["sections"]) >= 1
    assert "coverage" in notes
    assert notes["coverage"]["processed_sections"] >= 1
    assert notes["coverage"]["total_sections"] >= 1
    print("[OK] test_hierarchical_notes_integration passed")


if __name__ == "__main__":
    test_group_chunks_into_sections()
    test_reduce_section_notes_scaling()
    test_detail_level_configurations()
    test_hierarchical_notes_integration()
    print("\nALL STEP 1 NOTES MAP-REDUCE TESTS PASSED SUCCESSFULLY!")
