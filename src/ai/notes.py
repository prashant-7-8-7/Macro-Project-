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
    max_retries: int = 2,
    allow_fallback: bool = False,
) -> Dict[str, Any]:
    """
    MAP phase: calls the LLM for a given section to extract high-fidelity,
    structured notes without aggressive shortening.
    Retries with backoff if rate-limited or error.
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

    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            raw_response = call_llm(prompt, max_attempts_per_model=2)
            if raw_response:
                parsed = _safe_parse_json(raw_response)
                if parsed and isinstance(parsed, dict):
                    parsed["status"] = "success"
                    parsed["page_range"] = page_label
                    parsed["section_index"] = section.get("section_index", 1)
                    return parsed
                else:
                    last_error = f"Malformed JSON from LLM: {raw_response[:80]}..."
            else:
                last_error = "Empty response from LLM (provider unavailable or rate-limited)."
        except Exception as e:
            last_error = str(e)
            logger.warning(
                "[Notes Map] Section %d attempt %d/%d failed: %s",
                section.get("section_index", 0),
                attempt,
                max_retries,
                e
            )

        if attempt < max_retries:
            import time
            time.sleep(0.8 * attempt)

    if allow_fallback:
        logger.warning(
            "[Notes Map] Section %d (%s) failed after %d retries. Using structured fallback.",
            section.get("section_index", 0),
            page_label,
            max_retries,
        )
        fb = _build_fallback_section(section, doc_title)
        fb["status"] = "success"
        return fb

    logger.error(
        "[Notes Map] Section %d (%s) failed after %d retries: %s",
        section.get("section_index", 0),
        page_label,
        max_retries,
        last_error
    )
    return {
        "status": "failed",
        "section_index": section.get("section_index", 1),
        "page_start": section.get("page_start", 1),
        "page_end": section.get("page_end", 1),
        "page_label": page_label,
        "error": last_error or f"Failed after {max_retries} retries.",
    }


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


def translate_section_notes(
    section_dict: Dict[str, Any],
    source_lang: str,
    target_lang: str = "en",
    max_retries: int = 2,
) -> Dict[str, Any]:
    """
    Translates a mapped/reduced section note from source_lang to target_lang.
    Preserves heading, explanation, bullets, keyBox, tip, layout, and color.
    Retains the original technical term in brackets beside translated terms
    (e.g., 'गतिज ऊर्जा [Kinetic Energy]' or 'Depth-First Search [गहन-प्रथम खोज]').
    """
    if not section_dict or source_lang == target_lang:
        return section_dict

    source_lang_name = LANGUAGE_NAMES.get(source_lang, source_lang)
    target_lang_name = LANGUAGE_NAMES.get(target_lang, target_lang)

    payload = {
        "heading": section_dict.get("heading", ""),
        "explanation": section_dict.get("content", section_dict.get("explanation", "")),
        "bullets": section_dict.get("bullets", []),
        "keyBox": section_dict.get("keyBox", {}),
        "tip": section_dict.get("tip", ""),
    }

    prompt = f"""You are an expert multilingual academic translator.
Translate the following study notes section from {source_lang_name} ({source_lang}) into {target_lang_name} ({target_lang}).

RULES:
1. Translate all headings, explanations, bullets, key terms, and tips naturally and accurately into {target_lang_name}.
2. TECHNICAL TERMS: For all significant technical, computational, mathematical, scientific, or domain-specific terms, preserve the original term in brackets beside the translation (for example: "गतिज ऊर्जा [Kinetic Energy]" or "Depth-First Search [गहन-प्रथम खोज]").
3. PRESERVE STRUCTURE: Keep the exact same JSON schema and layout. Do not invent or drop any bullet points.
4. Return ONLY valid JSON (no markdown code blocks, no preamble).

SECTION JSON TO TRANSLATE:
{json.dumps(payload, ensure_ascii=False, indent=2)}

Return ONLY the raw JSON object."""

    for attempt in range(1, max_retries + 1):
        try:
            raw_response = call_llm(prompt, max_attempts_per_model=2)
            if raw_response:
                parsed = _safe_parse_json(raw_response)
                if parsed and isinstance(parsed, dict):
                    translated = dict(section_dict)
                    if parsed.get("heading"):
                        translated["heading"] = parsed["heading"]
                    if parsed.get("explanation"):
                        translated["content"] = parsed["explanation"]
                        translated["explanation"] = parsed["explanation"]
                    if parsed.get("bullets") and isinstance(parsed["bullets"], list):
                        translated["bullets"] = parsed["bullets"]
                    if parsed.get("keyBox") and isinstance(parsed["keyBox"], dict):
                        translated["keyBox"] = parsed["keyBox"]
                    if parsed.get("tip"):
                        translated["tip"] = parsed["tip"]
                    translated["language"] = target_lang
                    return translated
        except Exception as e:
            logger.warning("[Notes Translate] Attempt %d failed: %s", attempt, e)

    return dict(section_dict)


def translate_full_notes(
    notes: Dict[str, Any],
    source_lang: str,
    target_lang: str = "en",
) -> Dict[str, Any]:
    """
    Translates an entire structured notes document section-by-section from source_lang to target_lang.
    Keeps identical headings, order, section numbers, layouts, colors, and coverage.
    """
    if not notes or source_lang == target_lang:
        return notes

    source_lang_name = LANGUAGE_NAMES.get(source_lang, source_lang)
    target_lang_name = LANGUAGE_NAMES.get(target_lang, target_lang)

    translated_sections = []
    for sec in notes.get("sections", []):
        tr_sec = translate_section_notes(
            section_dict=sec,
            source_lang=source_lang,
            target_lang=target_lang,
        )
        translated_sections.append(tr_sec)

    translated_notes = dict(notes)
    translated_notes["sections"] = translated_sections
    translated_notes["language"] = target_lang
    translated_notes["language_name"] = target_lang_name
    translated_notes["subject"] = f"Study Notes ({len(translated_sections)} Sections - {target_lang_name})"

    if translated_sections:
        translated_notes["keyTakeaways"] = [
            sec["bullets"][0] for sec in translated_sections if sec.get("bullets")
        ][:8]
        translated_notes["remember"] = [
            sec["keyBox"]["items"][0]
            for sec in translated_sections
            if sec.get("keyBox") and sec["keyBox"].get("items")
        ][:6]

    return translated_notes


def generate_hierarchical_notes(
    chunks: List[Dict[str, Any]],
    doc_title: str,
    detail_level: str = "standard",
    doc_lang: Optional[str] = None,
    allow_fallback: bool = False,
    notes_language: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Main map-reduce notes generator:
    1. Group chunks into ~6k-8k sections respecting page boundaries.
    2. MAP: Extract comprehensive notes per section, tracking any sections that fail.
    3. REDUCE: Hierarchically combine all successful sections into full-length notes.
    4. COVERAGE: Accurately record processed vs skipped pages/sections and provide retry hooks.
    5. LANGUAGES: Support 'original', 'en', or 'both'. In 'both' mode, generate once and translate section-by-section.
    """
    if not chunks:
        return {"notes": None, "error": "No document content found."}

    # Detect language if not provided
    sample_text = " ".join(c.get("content", "") for c in chunks[:3])
    detected_lang = doc_lang or chunks[0].get("language") or detect_text_language(sample_text)

    # Determine generation language and dual mode
    notes_lang_mode = (notes_language or "original").lower().strip()
    if notes_lang_mode in ("both", "dual"):
        is_both_mode = True
        target_gen_lang = detected_lang if detected_lang != "en" else "en"
    elif notes_lang_mode in ("en", "english"):
        is_both_mode = False
        target_gen_lang = "en"
    elif notes_lang_mode == "original" or not notes_lang_mode:
        is_both_mode = False
        target_gen_lang = detected_lang
    else:
        is_both_mode = False
        target_gen_lang = notes_lang_mode

    # 1. Group chunks into page-aligned sections
    sections = group_chunks_into_sections(chunks)
    if not sections:
        return {"notes": None, "error": "Document contains no readable text."}

    total_pages = max(int(c.get("page_number") or 1) for c in chunks)
    min_page = min(int(c.get("page_number") or 1) for c in chunks)
    coverage_label = f"pages {min_page}-{total_pages} of {total_pages} ({len(sections)} sections)"

    logger.info(
        "[Notes] Generating notes for '%s' (%s, detail=%s, gen_lang=%s, mode=%s)",
        doc_title,
        coverage_label,
        detail_level,
        target_gen_lang,
        notes_lang_mode,
    )

    # 2. MAP: Extract notes for each section
    successful_sections: List[Dict[str, Any]] = []
    failed_sections: List[Dict[str, Any]] = []

    for sec in sections:
        mapped = map_section_to_notes(
            section=sec,
            doc_title=doc_title,
            detail_level=detail_level,
            doc_lang=target_gen_lang,
            max_retries=2,
            allow_fallback=allow_fallback,
        )
        if mapped.get("status") == "failed":
            failed_sections.append({
                "section_index": sec.get("section_index", 1),
                "page_start": sec.get("page_start", 1),
                "page_end": sec.get("page_end", 1),
                "page_label": sec.get("page_label", f"p. {sec.get('page_start', 1)}"),
                "error": mapped.get("error", "Generation failed"),
            })
        else:
            successful_sections.append(mapped)

    # 3. REDUCE: Combine successful sections into scalable notebook format
    if successful_sections:
        final_notes = reduce_section_notes(
            section_notes_list=successful_sections,
            doc_title=doc_title,
            detail_level=detail_level,
            doc_lang=target_gen_lang,
            total_pages_covered=coverage_label,
        )
    else:
        final_notes = {
            "title": doc_title or "Study Notes",
            "subject": f"Study Notes (0 of {len(sections)} sections generated)",
            "quote": "All sections failed after retries. Please verify your connection or click Retry.",
            "detail_level": detail_level,
            "sections": [],
            "keyTakeaways": [],
            "remember": [],
        }

    # 4. COVERAGE CHECK
    if not failed_sections:
        coverage_text = f"Covered pages {min_page}-{total_pages} of {total_pages} — {len(sections)} sections"
        skipped_pages_text = None
    else:
        skipped_labels = [fs["page_label"] for fs in failed_sections]
        coverage_text = f"Covered {len(successful_sections)} of {len(sections)} sections (pages {min_page}-{total_pages})"
        skipped_pages_text = f"Skipped pages: {', '.join(skipped_labels)} ({len(failed_sections)} section{'s' if len(failed_sections) > 1 else ''} failed after retries)"

    final_notes["coverage"] = {
        "total_sections": len(sections),
        "processed_sections": len(successful_sections),
        "successful_section_indices": [s.get("section_index") for s in successful_sections],
        "failed_sections": failed_sections,
        "min_page": min_page,
        "max_page": total_pages,
        "coverage_text": coverage_text,
        "skipped_pages_text": skipped_pages_text,
    }

    final_notes["language"] = target_gen_lang
    final_notes["language_name"] = LANGUAGE_NAMES.get(target_gen_lang, target_gen_lang)
    final_notes["notes_mode"] = "both" if (is_both_mode and detected_lang != "en") else "single"

    # 5. DUAL NOTES (if both requested and source is not English)
    if is_both_mode and detected_lang != "en" and successful_sections:
        logger.info("[Notes] Translating final notes section-by-section into English for Dual View...")
        english_notes = translate_full_notes(
            notes=final_notes,
            source_lang=detected_lang,
            target_lang="en",
        )
        final_notes["dual_notes"] = {
            "original": dict(final_notes),
            "english": english_notes,
            "original_lang": detected_lang,
            "original_lang_name": LANGUAGE_NAMES.get(detected_lang, detected_lang),
        }

    return {"notes": final_notes}


def retry_failed_sections(
    chunks: List[Dict[str, Any]],
    doc_title: str,
    target_section_indices: List[int],
    existing_notes: Dict[str, Any],
    detail_level: str = "standard",
    doc_lang: Optional[str] = None,
    allow_fallback: bool = False,
    notes_language: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Retries ONLY the specified failed sections.
    Newly succeeded sections are spliced into existing_notes in proper numerical/page order.
    Coverage tracking and summary fields are updated accordingly.
    """
    if not chunks or not existing_notes:
        return existing_notes or {}

    sections = group_chunks_into_sections(chunks)
    sections_by_index = {s["section_index"]: s for s in sections}

    total_pages = max(int(c.get("page_number") or 1) for c in chunks)
    min_page = min(int(c.get("page_number") or 1) for c in chunks)

    detected_lang = doc_lang or existing_notes.get("language") or "en"

    # Current sections in existing_notes
    current_sections = list(existing_notes.get("sections", []))
    existing_coverage = existing_notes.get("coverage", {})
    failed_sections_map = {
        fs["section_index"]: fs
        for fs in existing_coverage.get("failed_sections", [])
    }

    colors = ["green", "blue", "purple", "teal", "orange", "red"]

    for sec_idx in target_section_indices:
        sec = sections_by_index.get(sec_idx)
        if not sec:
            continue

        mapped = map_section_to_notes(
            section=sec,
            doc_title=doc_title,
            detail_level=detail_level,
            doc_lang=detected_lang,
            max_retries=2,
            allow_fallback=allow_fallback,
        )

        if mapped.get("status") != "failed":
            # Success! Format as a reduced section entry
            color = colors[(sec_idx - 1) % len(colors)]
            heading = mapped.get("heading") or f"Section {sec_idx}"
            page_range = mapped.get("page_range", sec.get("page_label", ""))
            if page_range and page_range not in heading:
                heading = f"{heading} ({page_range})"

            explanation = mapped.get("explanation", "")
            bullets = mapped.get("bullets", [])
            examples = mapped.get("examples", [])
            if examples and len(bullets) < 8:
                for ex in examples[:3]:
                    bullets.append(f"Example: {ex}")

            kb = mapped.get("keyBox")
            layout = "split" if (kb and kb.get("items")) else "full"

            new_sec_entry = {
                "number": sec_idx,
                "heading": heading,
                "color": color,
                "layout": layout,
                "content": explanation,
                "bullets": bullets,
                "keyBox": kb if kb else {"title": "⭐ Key Concept", "items": bullets[:2] if bullets else ["Core principle"]},
                "tip": mapped.get("tip") or f"Key takeaway from {page_range}"
            }

            # Replace or insert into current_sections
            found_idx = next((i for i, s in enumerate(current_sections) if s.get("number") == sec_idx), None)
            if found_idx is not None:
                current_sections[found_idx] = new_sec_entry
            else:
                current_sections.append(new_sec_entry)

            # Remove from failed sections map
            failed_sections_map.pop(sec_idx, None)
        else:
            # Still failed: update error info
            failed_sections_map[sec_idx] = {
                "section_index": sec_idx,
                "page_start": sec.get("page_start", 1),
                "page_end": sec.get("page_end", 1),
                "page_label": sec.get("page_label", f"p. {sec.get('page_start', 1)}"),
                "error": mapped.get("error", "Retry failed"),
            }

    # Sort current_sections by section number
    current_sections.sort(key=lambda s: int(s.get("number", 0)))
    existing_notes["sections"] = current_sections

    remaining_failed = list(failed_sections_map.values())
    remaining_failed.sort(key=lambda s: int(s.get("section_index", 0)))

    if not remaining_failed:
        coverage_text = f"Covered pages {min_page}-{total_pages} of {total_pages} — {len(sections)} sections"
        skipped_pages_text = None
    else:
        skipped_labels = [fs["page_label"] for fs in remaining_failed]
        coverage_text = f"Covered {len(current_sections)} of {len(sections)} sections (pages {min_page}-{total_pages})"
        skipped_pages_text = f"Skipped pages: {', '.join(skipped_labels)} ({len(remaining_failed)} section{'s' if len(remaining_failed) > 1 else ''} failed after retries)"

    existing_notes["coverage"] = {
        "total_sections": len(sections),
        "processed_sections": len(current_sections),
        "successful_section_indices": [s.get("number") for s in current_sections],
        "failed_sections": remaining_failed,
        "min_page": min_page,
        "max_page": total_pages,
        "coverage_text": coverage_text,
        "skipped_pages_text": skipped_pages_text,
    }

    # If in dual mode, update the translated dual version as well
    if existing_notes.get("dual_notes"):
        orig_lang = existing_notes["dual_notes"].get("original_lang", detected_lang)
        english_notes = translate_full_notes(
            notes=existing_notes,
            source_lang=orig_lang,
            target_lang="en",
        )
        existing_notes["dual_notes"]["original"] = dict(existing_notes)
        existing_notes["dual_notes"]["english"] = english_notes

    return existing_notes


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
