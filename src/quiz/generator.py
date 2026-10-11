import json
import logging
import os
from typing import List, Dict

from dotenv import load_dotenv
from src.quiz.schemas import QuizQuestion
from src.ai.rag import call_llm

load_dotenv()

logger = logging.getLogger(__name__)    

MODEL_NAME = "llama-3.3-70b-versatile"


def generate_questions(
    contexts: List[Dict],
    num_questions: int = 10,
    difficulty: str = "mixed",
) -> List[QuizQuestion]:
    """
    Generate candidate MCQs from retrieved document chunks.

    Important:
    Gemini is only responsible for generating candidates.
    Validation happens separately in validator.py.
    """

    if not contexts:
        return []

    # If there are many chunks, sample diverse chunks to prevent token limits
    if len(contexts) > 40:
        step = max(1, len(contexts) // 30)
        selected_contexts = contexts[::step][:35]
    else:
        selected_contexts = contexts

    source_text = []
    for i, ctx in enumerate(selected_contexts):
        source_text.append(
            f"""
SOURCE {i + 1}
Chunk ID: {ctx.get('chunk_index', '')}
Page: {ctx.get('page_number', 1)}

{ctx.get('content', '')}
"""
        )

    context_block = "\n".join(source_text)

    prompt = f"""
You are a question-generation component inside a document assessment system.

Generate exactly {num_questions} multiple-choice questions from ONLY the
provided document content.

Requested difficulty: {difficulty}

Rules:
1. Do not use outside knowledge.
2. Every question must be answerable from the provided content.
3. Each question must have exactly 4 options.
4. Exactly one option must be correct.
5. Avoid ambiguous questions.
6. Avoid questions whose answer is not explicitly supported by the source.
7. Do not create duplicate or nearly duplicate questions.
8. Identify the source page and source chunk ID.
9. Classify each question with a topic.
10. Classify each question using one Bloom level:
    Remember, Understand, Apply, Analyze.
11. Return ONLY valid JSON.
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
    "difficulty": "easy|medium|hard",
    "bloom_level": "Remember|Understand|Apply|Analyze",
    "source_page": 1,
    "source_chunk_id": "..."
  }}
]

DOCUMENT CONTENT:
{context_block}
"""

    try:
        raw_text = call_llm(
            prompt,
            max_attempts_per_model=2,
        )

        if not raw_text:
            raise RuntimeError("All AI models are currently unavailable.")

        raw_text = raw_text.strip()

        # Robust JSON extraction: Find the first '[' and last ']'
        start_idx = raw_text.find('[')
        end_idx = raw_text.rfind(']')

        if start_idx != -1 and end_idx != -1 and end_idx >= start_idx:
            json_str = raw_text[start_idx:end_idx+1]
        else:
            json_str = raw_text

        data = json.loads(json_str)

        if not isinstance(data, list):
            raise ValueError("AI response is not a JSON list.")

        questions = []

        for item in data:
            try:
                question = QuizQuestion(
                    question=item["question"],
                    options=item["options"],
                    correct_answer=item["correct_answer"],
                    topic=item.get("topic"),
                    difficulty=item.get("difficulty"),
                    bloom_level=item.get("bloom_level"),
                    source_page=item.get("source_page"),
                    source_chunk_id=item.get("source_chunk_id"),
                )

                questions.append(question)

            except Exception as exc:
                logger.warning(
                    "Skipping malformed generated question: %s",
                    exc,
                )

        return questions

    except json.JSONDecodeError as exc:
        logger.exception("Gemini returned invalid JSON.")
        raise RuntimeError("Question generator returned invalid JSON.") from exc

    except Exception:
        logger.exception("Question generation failed.")
        raise