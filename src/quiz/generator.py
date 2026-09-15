import json
import logging
import os
from typing import List, Dict

from dotenv import load_dotenv
from google import genai

from src.quiz.schemas import QuizQuestion

load_dotenv()

logger = logging.getLogger(__name__)    

MODEL_NAME = "gemini-3.5-flash"


def _get_client():
    api_key = os.environ.get("GEMINI_API_KEY")

    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not configured.")

    return genai.Client(api_key=api_key)


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

    source_text = []

    for i, ctx in enumerate(contexts):
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

    client = _get_client()

    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
        )

        raw_text = response.text.strip()

        # Handle accidental markdown fences.
        if raw_text.startswith("```"):
            raw_text = raw_text.replace("```json", "", 1)
            raw_text = raw_text.replace("```", "")
            raw_text = raw_text.strip()

        data = json.loads(raw_text)

        if not isinstance(data, list):
            raise ValueError("Gemini response is not a JSON list.")

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