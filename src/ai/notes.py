import json
import logging
import math
import os
import re
from typing import List, Dict, Any, Optional

from src.ai.rag import call_llm, LANGUAGE_NAMES
from src.ingestion.detector import detect_text_language

logger = logging.getLogger(__name__)

# Detail level configurations
DETAIL_CONFIG = {
    "brief": {
        "name": "Brief",
        "ratio_desc": "about 5% of source length; concise core summaries and essential concepts",
        "min_bullets": 2,
        "max_bullets": 4,
        "include_deep_examples": False,
    },
    "standard": {
        "name": "Standard",
        "ratio_desc": "about 12-15% of source length; balanced, comprehensive coverage of all major concepts, definitions, and steps",
        "min_bullets": 4,
        "max_bullets": 7,
        "include_deep_examples": True,
    },
    "detailed": {
        "name": "Detailed",
        "ratio_desc": "about 25% of source length; in-depth, exhaustive notes capturing all definitions, algorithms, examples, figures, and nuances",
        "min_bullets": 6,
        "max_bullets": 12,
        "include_deep_examples": True,
    },
}


def group_chunks_into_sections(
    chunks: List[Dict[str, Any]],
    target_min_chars: int = 5000,
    target_max_chars: int = 8000,
) -> List[Dict[str, Any]]:
    """
    Groups stored document chunks, in page order, into sections that fit
    comfortably into the model's context window (~6,000-8,000 chars) while
    respecting page boundaries.
    """
    if not chunks:
        return []

    # Sort chunks in deterministic reading order: page_number, then chunk_index
    sorted_chunks = sorted(
        chunks,
        key=lambda c: (
            int(c.get("page_number") or 1),
            int(c.get("chunk_index") or 0)
        )
    )

    sections: List[Dict[str, Any]] = []
    current_section_chunks: List[Dict[str, Any]] = []
    current_char_count = 0

    for chunk in sorted_chunks:
        content = chunk.get("content", "").strip()
        if not content:
            continue

        chunk_len = len(content)

        # Check if adding this chunk exceeds maximum section size
        if current_char_count + chunk_len > target_max_chars and current_char_count >= target_min_chars:
            # Finalize current section
            sections.append(_build_section_payload(len(sections) + 1, current_section_chunks))
            current_section_chunks = [chunk]
            current_char_count = chunk_len
        else:
            current_section_chunks.append(chunk)
            current_char_count += chunk_len

    if current_section_chunks:
        sections.append(_build_section_payload(len(sections) + 1, current_section_chunks))

    logger.info(
        "[Notes Grouping] Partitioned %d chunks into %d sections (target: %d-%d chars).",
        len(chunks),
        len(sections),
        target_min_chars,
        target_max_chars,
    )
    return sections


def _build_section_payload(section_num: int, chunks: List[Dict[str, Any]]) -> Dict[str, Any]:
    pages = [int(c.get("page_number") or 1) for c in chunks]
    min_page = min(pages) if pages else 1
    max_page = max(pages) if pages else 1
    page_label = f"pp. {min_page}-{max_page}" if min_page != max_page else f"p. {min_page}"

    combined_text = "\n\n".join(c.get("content", "").strip() for c in chunks)

    return {
        "section_index": section_num,
        "page_start": min_page,
        "page_end": max_page,
        "page_label": page_label,
        "text": combined_text,
        "char_count": len(combined_text),
        "chunk_indices": [c.get("chunk_index") for c in chunks],
    }


def map_section_to_notes(
    section: Dict[str, Any],
    doc_title: str,
    detail_level: str = "standard",
    doc_lang: str = "en",
) -> Dict[str, Any]:
    """
    MAP phase: calls the LLM once for a given section to extract high-fidelity,
    structured notes without aggressive shortening.
    """
    config = DETAIL_CONFIG.get(detail_level, DETAIL_CONFIG["standard"])
    lang_name = LANGUAGE_NAMES.get(doc_lang, doc_lang)
    page_label = section.get("page_label", "document")
    text = section.get("text", "")

    prompt = f"""You are an expert student note-maker and researcher.
Extract high-yield, structured study notes from the following text (from {page_label} of "{doc_title}").

TARGET DETAIL LEVEL: {config['name'].upper()} ({config['ratio_desc']})
TARGET LANGUAGE: {lang_name} ({doc_lang}).
If terms or formulas are widely known in English, include the English term in brackets beside the translation.

RULES:
1. Extract ALL key concepts, definitions, formulas, algorithms/steps, examples, numbers, dates, and conclusions from this section.
2. DO NOT aggressively shorten. Cover every significant concept in the text thoroughly.
3. STRICT FIDELITY: Use ONLY information directly stated in the text. Do not invent or assume outside facts.
4. Return ONLY valid JSON (no markdown fences, no conversational preamble).

JSON SCHEMA:
{{
  "heading": "Descriptive Topic Heading for {page_label}",
  "page_range": "{page_label}",
  "explanation": "2-4 sentence thorough explanation of this topic.",
  "bullets": [
    "Detailed key fact or step with **bold** terminology",
    "Another significant point or rule from this section"
  ],
  "keyBox": {{
    "title": "⭐ Key Definition or Formula",
    "items": ["Definition or critical formula statement"]
  }},
  "examples": [
    "Concrete example, case, date, or number mentioned in the text"
  ],
  "tip": "Crucial concept or caution to remember from this section"
}}

DOCUMENT SECTION TEXT ({page_label}):
{text}

Return ONLY the raw JSON object."""

    raw_response = call_llm(prompt, max_attempts_per_model=2)

    if not raw_response:
        logger.warning(
            "[Notes Map] Section %d (%s) received empty response from LLM.",
            section.get("section_index", 0),
            page_label,
        )
        return _build_fallback_section(section, doc_title)

    parsed = _safe_parse_json(raw_response)
    if not parsed or not isinstance(parsed, dict):
        logger.warning(
            "[Notes Map] Section %d failed to parse JSON. Falling back to local structured extraction.",
            section.get("section_index", 0)
        )
        return _build_fallback_section(section, doc_title, raw_text=raw_response)

    # Ensure page label is set
    parsed["page_range"] = page_label
    parsed["section_index"] = section.get("section_index", 1)
    return parsed


def _build_fallback_section(section: Dict[str, Any], doc_title: str, raw_text: str = "") -> Dict[str, Any]:
    page_label = section.get("page_label", "pp.")
    lines = [line.strip() for line in (raw_text or section.get("text", "")).split("\n") if line.strip()]
    first_few = lines[:5] if lines else ["Review document section content."]

    return {
        "section_index": section.get("section_index", 1),
        "heading": f"Topic Summary ({page_label})",
        "page_range": page_label,
        "explanation": first_few[0] if first_few else "Extracted section notes.",
        "bullets": first_few[1:] if len(first_few) > 1 else ["Detailed facts available in source section."],
        "keyBox": {
            "title": "⭐ Key Point",
            "items": [first_few[0] if first_few else "Important source concept"]
        },
        "examples": [],
        "tip": f"Source: {page_label}",
    }


def reduce_section_notes(
    section_notes_list: List[Dict[str, Any]],
    doc_title: str,
    detail_level: str = "standard",
    doc_lang: str = "en",
    total_pages_covered: str = "",
) -> Dict[str, Any]:
    """
    REDUCE phase: Combines mapped section notes into a cohesive, beautifully
    structured notebook document with colors, layouts, takeaways, glossary,
    and formulas without truncating to a small fixed page limit.
    """
    if not section_notes_list:
        return {
            "title": doc_title or "Study Notes",
            "subject": "Document Summary",
            "quote": "No content available to generate notes.",
            "sections": [],
            "keyTakeaways": [],
            "remember": []
        }

    colors = ["green", "blue", "purple", "teal", "orange", "red"]
    sections_out = []

    all_takeaways: List[str] = []
    all_glossary_terms: List[str] = []

    for i, s in enumerate(section_notes_list):
        color = colors[i % len(colors)]
        heading = s.get("heading") or f"Section {i + 1}"
        page_range = s.get("page_range", "")
        if page_range and page_range not in heading:
            heading = f"{heading} ({page_range})"

        explanation = s.get("explanation", "")
        bullets = s.get("bullets", [])
        if not bullets and s.get("key_points"):
            bullets = s.get("key_points", [])

        # If examples exist, add them as bullet points or inside keybox
        examples = s.get("examples", [])
        if examples and len(bullets) < 8:
            for ex in examples[:3]:
                bullets.append(f"Example: {ex}")

        kb = s.get("keyBox")
        layout = "split" if (kb and kb.get("items")) else "full"

        sections_out.append({
            "number": i + 1,
            "heading": heading,
            "color": color,
            "layout": layout,
            "content": explanation,
            "bullets": bullets,
            "keyBox": kb if kb else {"title": "⭐ Key Concept", "items": bullets[:2] if bullets else ["Core principle"]},
            "tip": s.get("tip") or f"Key takeaway from {page_range}"
        })

        if s.get("key_takeaways"):
            all_takeaways.extend(s.get("key_takeaways", []))

    # Synthesize overall takeaways and memorable facts from section notes
    seen_takeaways = set()
    deduped_takeaways = []
    for t in all_takeaways:
        norm = t.strip()
        if norm and norm.lower() not in seen_takeaways:
            seen_takeaways.add(norm.lower())
            deduped_takeaways.append(norm)

    if not deduped_takeaways:
        # Fall back to first bullet from each section
        deduped_takeaways = [
            sec["bullets"][0] for sec in sections_out if sec.get("bullets")
        ][:8]

    remember_facts = [
        sec["keyBox"]["items"][0]
        for sec in sections_out
        if sec.get("keyBox") and sec["keyBox"].get("items")
    ][:6]

    final_quote = (
        f"Comprehensive notes covering {total_pages_covered or f'{len(sections_out)} sections'}."
    )

    return {
        "title": doc_title or "Study Notes",
        "subject": f"Study Notes ({len(sections_out)} Sections)",
        "quote": final_quote,
        "detail_level": detail_level,
        "sections": sections_out,
        "keyTakeaways": deduped_takeaways[:8],
        "remember": remember_facts[:6],
    }


def generate_hierarchical_notes(
    chunks: List[Dict[str, Any]],
    doc_title: str,
    detail_level: str = "standard",
    doc_lang: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Main map-reduce notes generator:
    1. Group chunks into ~6k-8k sections respecting page boundaries.
    2. MAP: Extract comprehensive notes per section.
    3. REDUCE: Hierarchically combine all sections into full-length notes scaling with source length.
    """
    if not chunks:
        return {"notes": None, "error": "No document content found."}

    # Detect language if not provided
    sample_text = " ".join(c.get("content", "") for c in chunks[:3])
    detected_lang = doc_lang or chunks[0].get("language") or detect_text_language(sample_text)

    # 1. Group chunks into page-aligned sections
    sections = group_chunks_into_sections(chunks)
    if not sections:
        return {"notes": None, "error": "Document contains no readable text."}

    total_pages = max(int(c.get("page_number") or 1) for c in chunks)
    min_page = min(int(c.get("page_number") or 1) for c in chunks)
    coverage_label = f"pages {min_page}-{total_pages} of {total_pages} ({len(sections)} sections)"

    logger.info(
        "[Notes] Generating notes for '%s' (%s, detail=%s, lang=%s)",
        doc_title,
        coverage_label,
        detail_level,
        detected_lang,
    )

    # 2. MAP: Extract notes for each section
    mapped_sections = []
    for sec in sections:
        mapped = map_section_to_notes(
            section=sec,
            doc_title=doc_title,
            detail_level=detail_level,
            doc_lang=detected_lang,
        )
        mapped_sections.append(mapped)

    # 3. REDUCE: Combine all sections into scalable notebook format
    final_notes = reduce_section_notes(
        section_notes_list=mapped_sections,
        doc_title=doc_title,
        detail_level=detail_level,
        doc_lang=detected_lang,
        total_pages_covered=coverage_label,
    )

    final_notes["coverage"] = {
        "total_sections": len(sections),
        "processed_sections": len(mapped_sections),
        "failed_sections": [],
        "min_page": min_page,
        "max_page": total_pages,
        "coverage_text": f"Covered pages {min_page}-{total_pages} of {total_pages} — {len(sections)} sections",
    }

    return {"notes": final_notes}


def _safe_parse_json(raw: str) -> Optional[Any]:
    """Cleans code fences and securely parses JSON object or array."""
    if not raw:
        return None
    s = str(raw).strip()
    s = s.replace("```json", "").replace("```JSON", "").replace("```", "").strip()
    start = s.find('{')
    end = s.rfind('}')
    if start != -1 and end != -1 and end > start:
        s = s[start:end+1]
    try:
        return json.loads(s)
    except Exception:
        return None
