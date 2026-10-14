import sys
from pathlib import Path
import uuid

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.ingestion.detector import detect_text_language, detect_document_language
from src.database.db import init_db, get_connection
from src.database.repository import DocumentRepository

def test_language_detection_multilingual():
    test_cases = {
        "en": "Artificial intelligence and distributed retrieval pipelines represent modern search.",
        "hi": "कृत्रिम बुद्धिमत्ता और तंत्रिका नेटवर्क आधुनिक खोज प्रणाली का हिस्सा हैं।",
        "es": "El procesamiento del lenguaje natural permite la comprensión de documentos en múltiples idiomas.",
        "ar": "تتيح معالجة اللغة الطبيعية والذكاء الاصطناعي استرجاع المعلومات بكفاءة عالية.",
        "zh": "人工智能和自然语言处理技术能够实现跨语言的高效文档检索与问答。",
        "ja": "自然言語処理と機械学習を使用して、多言語ドキュメントを正確に検索します。",
        "ru": "Искусственный интеллект и машинное обучение позволяют эффективно анализировать документы.",
        "ta": "இயற்கை மொழி செயலாக்கம் மற்றும் செயற்கை நுண்ணறிவு பல மொழி ஆவணங்களை பகுப்பாய்வு செய்கிறது.",
        "bn": "কৃত্রিম বুদ্ধিমত্তা এবং প্রাকৃতিক ভাষা প্রক্রিয়াকরণ বহুভাষিক নথি পুনরুদ্ধার সক্ষম করে।",
        "fr": "L'intelligence artificielle et l'apprentissage automatique facilitent l'analyse des textes."
    }

    for expected_lang, text in test_cases.items():
        detected = detect_text_language(text)
        assert detected == expected_lang, f"Failed for {expected_lang}: detected '{detected}' instead"
        print(f"[OK] Detected {expected_lang} accurately: '{detected}'")

    print("[OK] test_language_detection_multilingual passed")

def test_db_migration_and_language_column():
    # Run init_db which includes migration
    init_db()

    conn = get_connection()
    c = conn.cursor()
    c.execute("PRAGMA table_info(documents);")
    columns = [row["name"] if hasattr(row, "keys") else row[1] for row in c.fetchall()]
    conn.close()

    assert "language" in columns, f"Column 'language' missing from documents table: {columns}"
    print("[OK] Verified 'language' column in documents table")

    # Test inserting with specific language code
    repo = DocumentRepository()
    test_id = str(uuid.uuid4())
    test_hash = str(uuid.uuid4())
    success = repo.insert_document(
        doc_id=test_id,
        title="Hindi Test Doc",
        filename="hindi_sample.txt",
        file_type="txt",
        file_size=120,
        doc_hash=test_hash,
        metadata={"note": "test"},
        language="hi"
    )
    assert success is True

    # Query back
    docs = repo.get_all_documents()
    found = next((d for d in docs if d["id"] == test_id), None)
    assert found is not None
    assert found["language"] == "hi", f"Expected 'hi', got '{found['language']}'"
    print("[OK] Verified document insertion and language retrieval: 'hi'")

    # Clean up test row
    repo.delete_document(test_id)
    print("[OK] test_db_migration_and_language_column passed")

if __name__ == "__main__":
    test_language_detection_multilingual()
    test_db_migration_and_language_column()
    print("\nALL STEP 2 LANGUAGE DETECTION TESTS PASSED SUCCESSFULLY!")
