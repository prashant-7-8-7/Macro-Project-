import json
import logging
import math
import os
from typing import List, Dict

from dotenv import load_dotenv
from src.quiz.schemas import QuizQuestion
from src.ai.rag import call_llm

load_dotenv()

logger = logging.getLogger(__name__)


def _sample_contexts_for_batch(contexts: List[Dict], batch_index: int, total_batches: int, max_chunks: int = 25) -> List[Dict]:
    """
    Sample chunks across the whole document.
    If the document has more than max_chunks, distributes sampling across batches.
    """
    total = len(contexts)
    if total <= max_chunks:
        return contexts

    # Sample evenly across the entire document
    step = max(1, total // max_chunks)
    sampled = contexts[::step][:max_chunks]
    return sampled


def _generate_single_batch(
    contexts: List[Dict],
    batch_size: int,
    difficulty: str,
    existing_questions: List[str],
    batch_idx: int,
    total_batches: int,
) -> List[QuizQuestion]:
    """Generate a single batch of questions using the LLM."""
    selected_contexts = _sample_contexts_for_batch(contexts, batch_idx, total_batches)

    source_text = []
    for i, ctx in enumerate(selected_contexts):
        chunk_idx = ctx.get('chunk_index', '')
        page_num = ctx.get('page_number', 1)
        content = ctx.get('content', '')
        source_text.append(
            f"SOURCE {i + 1}\nChunk ID: {chunk_idx}\nPage: {page_num}\n\n{content}\n"
        )

    context_block = "\n".join(source_text)

    # Negative hints to avoid duplicate stems
    existing_hints = ""
    if existing_questions:
        sample_existing = existing_questions[-8:]
        existing_hints = "\n7b. Do not generate questions identical or very similar to these previously created:\n" + "\n".join(
            f"    - {q}" for q in sample_existing
        )

    prompt = f"""
You are a question-generation component inside a document assessment system.

Generate exactly {batch_size} multiple-choice questions from ONLY the
provided document content.

Requested difficulty: {difficulty}

Rules:
1. Do not use outside knowledge.
2. Every question must be answerable from the provided content.
3. Each question must have exactly 4 options.
4. Exactly one option must be correct.
5. Avoid ambiguous questions.
6. Avoid questions whose answer is not explicitly supported by the source.
7. Do not create duplicate or nearly duplicate questions.{existing_hints}
8. Identify the source page and source chunk ID.
9. Classify each question with a topic.
10. Classify each question using one Bloom level:
    Remember, Understand, Apply, Analyze.
11. Return ONLY valid JSON array.
12. Do not wrap the JSON in markdown.

JSON format:

[
  {{
    "question": "...",
    "options": [
      {{"label": "...", "is_correct": false}},
      {{"label": "...", "is_correct": true}},
      {{"label": "...", "is_correct": false}},
      {{"label": "...", "is_correct": false}}
    ],
    "correct_answer": "...",
    "topic": "...",
    "difficulty": "{difficulty}",
    "bloom_level": "Remember|Understand|Apply|Analyze",
    "source_page": 1,
    "source_chunk_id": "0"
  }}
]

DOCUMENT CONTENT:
{context_block}
"""

    logger.info(
        "[Quiz Generator] Batch %d/%d: Requesting %d questions (difficulty=%s). Context chunks: %d, context chars: %d",
        batch_idx + 1,
        total_batches,
        batch_size,
        difficulty,
        len(selected_contexts),
        len(context_block),
    )

    try:
        raw_text = call_llm(
            prompt,
            max_attempts_per_model=2,
        )

        if not raw_text:
            logger.warning("[Quiz Generator] Batch %d returned empty response from LLM.", batch_idx + 1)
            return []

        raw_text = raw_text.strip()
        start_idx = raw_text.find('[')
        end_idx = raw_text.rfind(']')

        if start_idx != -1 and end_idx != -1 and end_idx >= start_idx:
            json_str = raw_text[start_idx:end_idx+1]
        else:
            json_str = raw_text

        data = json.loads(json_str)

        if not isinstance(data, list):
            logger.warning("[Quiz Generator] Batch %d response is not a JSON list.", batch_idx + 1)
            return []

        questions = []
        for item in data:
            try:
                question = QuizQuestion(
                    question=item["question"],
                    options=item["options"],
                    correct_answer=item["correct_answer"],
                    topic=item.get("topic"),
                    difficulty=item.get("difficulty", difficulty),
                    bloom_level=item.get("bloom_level"),
                    source_page=item.get("source_page"),
                    source_chunk_id=item.get("source_chunk_id"),
                )
                questions.append(question)
            except Exception as exc:
                logger.warning(
                    "[Quiz Generator] Skipping malformed question in batch %d: %s",
                    batch_idx + 1,
                    exc,
                )

        logger.info(
            "[Quiz Generator] Batch %d/%d produced %d valid questions.",
            batch_idx + 1,
            total_batches,
            len(questions),
        )
        return questions

    except Exception as exc:
        logger.warning(
            "[Quiz Generator] Batch %d/%d encountered error: %s",
            batch_idx + 1,
            total_batches,
            exc,
        )
        return []


def generate_questions(
    contexts: List[Dict],
    num_questions: int = 10,
    difficulty: str = "mixed",
) -> List[QuizQuestion]:
    """
    Generate candidate MCQs from retrieved document chunks using batch generation.
    Batches are sized 3-5 questions per call and over-requests by ~1.3-1.5x to ensure sufficient pool.
    """
    if not contexts:
        return []

    # Over-request target to compensate for downstream validation drops
    over_request_target = math.ceil(num_questions * 1.35)
    batch_size = 4 if num_questions <= 6 else 5
    total_batches = max(1, math.ceil(over_request_target / batch_size))

    logger.info(
        "[Quiz Generator] Starting generation for requested=%d (over-request target=%d) in %d batches of max %d",
        num_questions,
        over_request_target,
        total_batches,
        batch_size,
    )

    all_questions: List[QuizQuestion] = []
    seen_stems = set()

    for batch_idx in range(total_batches):
        remaining_needed = over_request_target - len(all_questions)
        if remaining_needed <= 0:
            break

        current_batch_size = min(batch_size, remaining_needed)
        existing_stem_list = [q.question for q in all_questions]

        batch_questions = _generate_single_batch(
            contexts=contexts,
            batch_size=current_batch_size,
            difficulty=difficulty,
            existing_questions=existing_stem_list,
            batch_idx=batch_idx,
            total_batches=total_batches,
        )

        for q in batch_questions:
            normalized = " ".join(q.question.lower().split())
            if normalized not in seen_stems:
                seen_stems.add(normalized)
                all_questions.append(q)

        logger.info(
            "[Quiz Generator] Accumulated %d unique candidate questions after batch %d",
            len(all_questions),
            batch_idx + 1,
        )

    logger.info(
        "[Quiz Generator] Finished generation: %d unique candidate questions ready for validation (requested=%d).",
        len(all_questions),
        num_questions,
    )
    return all_questions