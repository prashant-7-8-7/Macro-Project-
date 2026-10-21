import logging
import re
import unicodedata
from typing import List, Dict, Tuple

from src.quiz.schemas import QuizQuestion

logger = logging.getLogger(__name__)


def _normalize_text(text: str) -> str:
    """Normalize text for comparison by lowercasing, NFKC normalizing, and stripping prefixes/punctuation."""
    if not text:
        return ""
    norm = unicodedata.normalize("NFKC", text.strip())
    # Strip common MCQ prefixes like "A)", "B.", "1-", etc.
    cleaned = re.sub(r'^[A-Da-d0-9][\).\:\-]\s*', '', norm)
    return cleaned.strip().lower()


def _extract_grounding_features(text: str) -> set:
    """
    Extracts Unicode word tokens and character 3-grams for robust grounding
    verification across all languages and scripts (Latin, Indic, CJK, Arabic, etc.).
    """
    if not text:
        return set()
    norm = unicodedata.normalize("NFKC", text).lower()

    # 1. Unicode word tokens
    words = {w for w in re.findall(r'[\w]+', norm, re.UNICODE) if len(w) >= 2}

    # 2. Character n-grams (3-grams) across non-punctuation/non-whitespace characters
    clean_chars = "".join(c for c in norm if not unicodedata.category(c).startswith(('P', 'Z', 'S', 'C')))
    ngrams = set()
    n = 3
    if len(clean_chars) >= n:
        for i in range(len(clean_chars) - n + 1):
            ngrams.add(clean_chars[i:i+n])
    elif clean_chars:
        ngrams.add(clean_chars)

    return words | ngrams


def validate_question(
    question: QuizQuestion,
    contexts: List[Dict],
) -> QuizQuestion:

    reasons = []

    # 1. Check question text
    if not question.question or not question.question.strip():
        reasons.append("Question text is empty.")

    # 2. Exactly 4 options
    if len(question.options) != 4:
        reasons.append("Question must have exactly four options.")

    # 3. Check option text
    if any(not option.label or not option.label.strip() for option in question.options):
        reasons.append("An option is empty.")

    # 4. Correct answer & is_correct alignment
    correct_options = [
        option for option in question.options
        if option.is_correct
    ]

    norm_ans = _normalize_text(question.correct_answer)

    if len(correct_options) == 1:
        norm_marked = _normalize_text(correct_options[0].label)
        if norm_ans and norm_marked and norm_ans != norm_marked:
            # Check if correct_answer matches another option
            matched_other = [
                opt for opt in question.options
                if _normalize_text(opt.label) == norm_ans
            ]
            if len(matched_other) == 1:
                for opt in question.options:
                    opt.is_correct = (opt == matched_other[0])
                correct_options = matched_other
            else:
                # Synchronize answer text to the marked option
                question.correct_answer = correct_options[0].label.strip()
        else:
            question.correct_answer = correct_options[0].label.strip()
    else:
        # LLM marked 0 or multiple options as correct; try to rescue via correct_answer
        matched = [
            opt for opt in question.options
            if _normalize_text(opt.label) == norm_ans
        ]
        if len(matched) == 1:
            for opt in question.options:
                opt.is_correct = (opt == matched[0])
            correct_options = matched
        else:
            reasons.append("Question must have exactly one correct option.")

    # 5. Duplicate options check
    labels = [
        _normalize_text(option.label)
        for option in question.options
    ]

    if len(labels) != len(set(labels)):
        reasons.append("Duplicate answer options detected.")

    # A valid chunk ID alone is not evidence that the answer is supported.
    def evidence_text(text):
        return " ".join(unicodedata.normalize("NFKC", text or "").casefold().split())

    def contains_answer(content):
        answer = re.sub(r"^[A-Da-d][).:]\s+", "", question.correct_answer.strip())
        answer = evidence_text(answer)
        content = evidence_text(content)
        if not answer:
            return False
        # CJK phrases occur inside unsegmented sentences; other scripts use word boundaries.
        if re.search(r"[\u3400-\u9fff\u3040-\u30ff]", answer):
            return answer in content
        return bool(re.search(r"(?<!\w)" + re.escape(answer) + r"(?!\w)", content))

    raw_chunk_id = str(question.source_chunk_id or "").strip()
    quote = evidence_text(question.source_quote)
    q_features = _extract_grounding_features(question.question)
    candidates = []
    for ctx in contexts:
        content = ctx.get("content", "")
        if not contains_answer(content):
            continue
        if quote and (quote not in evidence_text(content) or not contains_answer(question.source_quote)):
            continue
        overlap = len(q_features & _extract_grounding_features(content))
        if overlap == 0:
            continue
        # Prefer a correctly cited chunk when it actually supports the answer.
        score = overlap + (5 if str(ctx.get("chunk_index")) == raw_chunk_id else 0)
        candidates.append((score, ctx))

    if candidates:
        source = max(candidates, key=lambda item: item[0])[1]
        question.source_chunk_id = str(source.get("chunk_index", 0))
        question.source_page = source.get("page_number", 1)
        if not question.source_quote:
            # Older callers remain compatible; new generation requests supply excerpts.
            question.source_quote = None
    else:
        reasons.append("Correct answer and supporting excerpt could not be found together in a source chunk.")

    # Final decision
    if reasons:
        question.status = "rejected"
        question.grounding_score = 0.0
        question.validation_reasons = reasons
    else:
        question.status = "verified"
        question.grounding_score = 1.0
        question.validation_reasons = []

    return question


def validate_questions(
    questions: List[QuizQuestion],
    contexts: List[Dict],
) -> Tuple[List[QuizQuestion], List[QuizQuestion]]:

    verified = []
    rejected = []

    seen_questions = set()

    for idx, question in enumerate(questions):

        normalized = " ".join(
            unicodedata.normalize("NFKC", question.question).lower().split()
        )

        # Duplicate question check
        if normalized in seen_questions:
            question.status = "rejected"
            question.grounding_score = 0.0
            question.validation_reasons = [
                "Duplicate question detected."
            ]
            rejected.append(question)
            logger.info(
                "[Quiz Validator] Rejected Q%d ('%s...'): Duplicate question detected.",
                idx + 1,
                question.question[:40],
            )
            continue

        seen_questions.add(normalized)

        validated = validate_question(
            question,
            contexts,
        )

        if validated.status == "verified":
            verified.append(validated)
            logger.info(
                "[Quiz Validator] Verified Q%d: '%s...'",
                idx + 1,
                validated.question[:40],
            )
        else:
            rejected.append(validated)
            logger.info(
                "[Quiz Validator] d) Rejected Q%d ('%s...'): %s (raw source_chunk_id: %s)",
                idx + 1,
                validated.question[:40],
                validated.validation_reasons,
                validated.source_chunk_id,
            )

    logger.info(
        "[Quiz Validator] Summary: %d verified, %d rejected out of %d candidates.",
        len(verified),
        len(rejected),
        len(questions),
    )

    return verified, rejected
