import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.quiz.schemas import QuizQuestion, QuizOption
from src.quiz.validator import validate_question, validate_questions, _extract_grounding_features
from src.ai.rag import (
    synthesize_answer,
    summarize_document,
    fallback_synthesize,
    generate_notes,
    LANGUAGE_NAMES,
    NO_CONTEXT_MESSAGES,
    AI_UNAVAILABLE_MESSAGES
)


def test_localized_no_context_and_fallback():
    """Verify synthesize_answer and fallback_synthesize respond in the user's question language."""
    # Hindi query without contexts
    hi_res = synthesize_answer("यह दस्तावेज़ किस बारे में है?", [])
    assert "दस्तावेज़" in hi_res["answer"] or "प्रासंगिक" in hi_res["answer"], f"Hindi no-context message failed: {hi_res['answer']}"

    # Spanish query without contexts
    es_res = synthesize_answer("¿De qué trata este documento?", [])
    assert "documentos relevantes" in es_res["answer"], f"Spanish no-context message failed: {es_res['answer']}"

    # Arabic query without contexts
    ar_res = synthesize_answer("ما هو موضوع هذا المستند؟", [])
    assert "مستندات" in ar_res["answer"], f"Arabic no-context message failed: {ar_res['answer']}"

    # Chinese query without contexts
    zh_res = synthesize_answer("这篇文档讲了什么内容？", [])
    assert "文档" in zh_res["answer"], f"Chinese no-context message failed: {zh_res['answer']}"

    # English query without contexts
    en_res = synthesize_answer("What is this document about?", [])
    assert "No relevant documents" in en_res["answer"], f"English no-context message failed: {en_res['answer']}"

    # Fallback messages
    hi_fb = fallback_synthesize("prompt", q_lang="hi")
    assert "एआई" in hi_fb

    es_fb = fallback_synthesize("prompt", q_lang="es")
    assert "IA" in es_fb

    print("[OK] test_localized_no_context_and_fallback passed")


def test_multilingual_grounding_hindi():
    """Verify Hindi questions ground correctly across multiple chunks."""
    contexts = [
        {
            "chunk_index": 0,
            "page_number": 1,
            "content": "भारत की राजधानी नई दिल्ली है। यहाँ ऐतिहासिक इमारतें जैसे लाल किला और कुतुब मीनार स्थित हैं।"
        },
        {
            "chunk_index": 1,
            "page_number": 2,
            "content": "मशीन लर्निंग कृत्रिम बुद्धिमत्ता का एक महत्वपूर्ण उपक्षेत्र है जो डेटा से सीखने वाले एल्गोरिदम विकसित करता है।"
        }
    ]

    # Question about chunk 1 with missing or invalid source_chunk_id
    q = QuizQuestion(
        question="मशीन लर्निंग किसका एक महत्वपूर्ण उपक्षेत्र है?",
        options=[
            QuizOption(label="कृत्रिम बुद्धिमत्ता", is_correct=True),
            QuizOption(label="भौतिकी", is_correct=False),
            QuizOption(label="रसायन विज्ञान", is_correct=False),
            QuizOption(label="जीव विज्ञान", is_correct=False),
        ],
        correct_answer="कृत्रिम बुद्धिमत्ता",
        source_chunk_id=None,
        source_page=None,
    )

    validated = validate_question(q, contexts)
    assert validated.status == "verified", f"Validation failed: {validated.validation_reasons}"
    assert validated.source_chunk_id == "1", f"Expected chunk '1', got '{validated.source_chunk_id}'"
    assert validated.source_page == 2
    print("[OK] test_multilingual_grounding_hindi passed")


def test_multilingual_grounding_chinese():
    """Verify Chinese questions (unsegmented text) ground correctly using character n-grams."""
    contexts = [
        {
            "chunk_index": 0,
            "page_number": 1,
            "content": "太阳系由太阳以及围绕它运转的天体组成，包括八大行星。"
        },
        {
            "chunk_index": 1,
            "page_number": 2,
            "content": "自然语言处理是计算机科学领域的一个重要方向，旨在让计算机理解人类语言。"
        }
    ]

    q = QuizQuestion(
        question="自然语言处理的目的是什么？",
        options=[
            QuizOption(label="让计算机理解人类语言", is_correct=True),
            QuizOption(label="研究天体运动", is_correct=False),
            QuizOption(label="制造太阳能电池", is_correct=False),
            QuizOption(label="开发新型合金", is_correct=False),
        ],
        correct_answer="让计算机理解人类语言",
        source_chunk_id=None,
        source_page=None,
    )

    validated = validate_question(q, contexts)
    assert validated.status == "verified", f"Validation failed: {validated.validation_reasons}"
    assert validated.source_chunk_id == "1", f"Expected chunk '1', got '{validated.source_chunk_id}'"
    print("[OK] test_multilingual_grounding_chinese passed")


def test_multilingual_grounding_arabic():
    """Verify Arabic questions ground correctly."""
    contexts = [
        {
            "chunk_index": 0,
            "page_number": 1,
            "content": "تعد مدينة القاهرة عاصمة جمهورية مصر العربية وأكبر مدنها من حيث عدد السكان."
        },
        {
            "chunk_index": 1,
            "page_number": 2,
            "content": "الشبكات العصبية الاصطناعية هي نماذج حسابية مستوحاة من الشبكات العصبية الحيوية في الدماغ البشري."
        }
    ]

    q = QuizQuestion(
        question="مم استوحيت الشبكات العصبية الاصطناعية؟",
        options=[
            QuizOption(label="الشبكات العصبية الحيوية في الدماغ", is_correct=True),
            QuizOption(label="حركة الكواكب والنجوم", is_correct=False),
            QuizOption(label="تدفق الأنهار في مصر", is_correct=False),
            QuizOption(label="هندسة الجسور الحديثة", is_correct=False),
        ],
        correct_answer="الشبكات العصبية الحيوية في الدماغ",
        source_chunk_id=None,
        source_page=None,
    )

    validated = validate_question(q, contexts)
    assert validated.status == "verified", f"Validation failed: {validated.validation_reasons}"
    assert validated.source_chunk_id == "1", f"Expected chunk '1', got '{validated.source_chunk_id}'"
    print("[OK] test_multilingual_grounding_arabic passed")


def test_multilingual_grounding_spanish():
    """Verify Spanish questions with accents ground correctly."""
    contexts = [
        {
            "chunk_index": 0,
            "page_number": 1,
            "content": "La fotosíntesis es el proceso bioquímico mediante el cual las plantas convierten la energía solar en glucosa."
        },
        {
            "chunk_index": 1,
            "page_number": 2,
            "content": "La Revolución Francesa fue un conflicto social y político que convulsionó Francia y otras naciones de Europa."
        }
    ]

    q = QuizQuestion(
        question="¿Qué proceso utilizan las plantas para convertir la energía solar?",
        options=[
            QuizOption(label="Fotosíntesis", is_correct=True),
            QuizOption(label="Respiración celular", is_correct=False),
            QuizOption(label="Fermentación", is_correct=False),
            QuizOption(label="Oxidación", is_correct=False),
        ],
        correct_answer="Fotosíntesis",
        explanation="Las plantas realizan fotosíntesis para convertir la luz solar en glucosa.",
        source_chunk_id=None,
        source_page=None,
    )

    validated = validate_question(q, contexts)
    assert validated.status == "verified", f"Validation failed: {validated.validation_reasons}"
    assert validated.source_chunk_id == "0", f"Expected chunk '0', got '{validated.source_chunk_id}'"
    assert validated.explanation is not None
    print("[OK] test_multilingual_grounding_spanish passed")


def test_english_grounding_regression():
    """Verify English questions still ground and validate perfectly."""
    contexts = [
        {
            "chunk_index": 0,
            "page_number": 1,
            "content": "Python is a high-level programming language known for its clear syntax and dynamic typing."
        },
        {
            "chunk_index": 1,
            "page_number": 2,
            "content": "Rust is a systems programming language focused on safety, speed, and concurrency."
        }
    ]

    q = QuizQuestion(
        question="Which language is focused on safety and memory concurrency?",
        options=[
            QuizOption(label="Rust", is_correct=True),
            QuizOption(label="Python", is_correct=False),
            QuizOption(label="BASIC", is_correct=False),
            QuizOption(label="Fortran", is_correct=False),
        ],
        correct_answer="Rust",
        explanation="Rust focuses on memory safety and concurrency.",
        source_chunk_id=None,
        source_page=None,
    )

    validated = validate_question(q, contexts)
    assert validated.status == "verified", f"Validation failed: {validated.validation_reasons}"
    assert validated.source_chunk_id == "1", f"Expected chunk '1', got '{validated.source_chunk_id}'"
    print("[OK] test_english_grounding_regression passed")


if __name__ == "__main__":
    test_localized_no_context_and_fallback()
    test_multilingual_grounding_hindi()
    test_multilingual_grounding_chinese()
    test_multilingual_grounding_arabic()
    test_multilingual_grounding_spanish()
    test_english_grounding_regression()
    print("\nALL STEP 5 TESTS PASSED SUCCESSFULLY!")
