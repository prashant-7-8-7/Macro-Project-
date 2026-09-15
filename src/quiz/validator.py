from typing import List, Dict, Tuple

from src.quiz.schemas import QuizQuestion


def validate_question(
    question: QuizQuestion,
    contexts: List[Dict],
) -> QuizQuestion:

    reasons = []

    # Check question text
    if not question.question.strip():
        reasons.append("Question text is empty.")

    # Exactly 4 options
    if len(question.options) != 4:
        reasons.append("Question must have exactly four options.")

    # Exactly one correct option
    correct_options = [
        option for option in question.options
        if option.is_correct
    ]

    if len(correct_options) != 1:
        reasons.append("Question must have exactly one correct option.")

    # Check option text
    if any(not option.label.strip() for option in question.options):
        reasons.append("An option is empty.")

    # Check correct answer
    if len(correct_options) == 1:
        if question.correct_answer.strip() != correct_options[0].label.strip():
            reasons.append(
                "Correct answer does not match the marked option."
            )

    # Duplicate options
    labels = [
        option.label.strip().lower()
        for option in question.options
    ]

    if len(labels) != len(set(labels)):
        reasons.append("Duplicate answer options detected.")

    # Source grounding
    valid_chunk_indexes = {
        str(context.get("chunk_index"))
        for context in contexts
    }

    if question.source_chunk_id is None:
        reasons.append("No source chunk provided.")
    elif str(question.source_chunk_id) not in valid_chunk_indexes:
        reasons.append("Referenced source chunk does not exist.")

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

    for question in questions:

        normalized = " ".join(
            question.question.lower().split()
        )

        # Duplicate question check
        if normalized in seen_questions:
            question.status = "rejected"
            question.grounding_score = 0.0
            question.validation_reasons = [
                "Duplicate question detected."
            ]
            rejected.append(question)
            continue

        seen_questions.add(normalized)

        validated = validate_question(
            question,
            contexts,
        )

        if validated.status == "verified":
            verified.append(validated)
        else:
            rejected.append(validated)

    return verified, rejected