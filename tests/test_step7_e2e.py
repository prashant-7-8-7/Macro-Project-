import sys
import os
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from starlette.testclient import TestClient
from src.api.routes import app


def has_devanagari(text: str) -> bool:
    return any(0x0900 <= ord(c) <= 0x097F for c in text)


def has_arabic(text: str) -> bool:
    return any(0x0600 <= ord(c) <= 0x06FF for c in text)


def has_cjk(text: str) -> bool:
    return any(0x4E00 <= ord(c) <= 0x9FFF for c in text)


def run_e2e_verification():
    client = TestClient(app)
    fixtures_dir = Path(__file__).resolve().parent / "fixtures"

    test_cases = [
        {
            "name": "Hindi TXT",
            "file": "hindi.txt",
            "lang": "Hindi (hi)",
            "expected_lang": "hi",
            "script_validator": has_devanagari,
            "question": "मशीन लर्निंग किसका एक महत्वपूर्ण उपक्षेत्र है?",
        },
        {
            "name": "Spanish TXT",
            "file": "spanish.txt",
            "lang": "Spanish (es)",
            "expected_lang": "es",
            "script_validator": lambda t: "energía" in t.lower() or "renovable" in t.lower() or "solar" in t.lower(),
            "question": "¿Cómo convierten los paneles fotovoltaicos la radiación solar?",
        },
        {
            "name": "Arabic TXT",
            "file": "arabic.txt",
            "lang": "Arabic (ar)",
            "expected_lang": "ar",
            "script_validator": has_arabic,
            "question": "ما هو الهدف من معالجة اللغات الطبيعية؟",
        },
        {
            "name": "Chinese TXT",
            "file": "chinese.txt",
            "lang": "Chinese (zh)",
            "expected_lang": "zh",
            "script_validator": has_cjk,
            "question": "词嵌入技术在自然语言处理中起什么作用？",
        },
        {
            "name": "Multilingual DOCX",
            "file": "multilingual_sample.docx",
            "lang": "Mixed (hi/es/en)",
            "expected_lang": None,  # Can be en, hi, or es depending on text proportion
            "script_validator": lambda t: has_devanagari(t) and ("tecnología" in t.lower() or "inteligencia" in t.lower()),
            "question": "What is machine learning according to the document table?",
        },
        {
            "name": "Spanish PDF",
            "file": "spanish.pdf",
            "lang": "Spanish (es)",
            "expected_lang": "es",
            "script_validator": lambda t: "solar" in t.lower() or "energias" in t.lower(),
            "question": "¿Qué fuente de energía limpia se describe en este documento?",
        },
        {
            "name": "Hindi PDF",
            "file": "hindi.pdf",
            "lang": "Hindi (hi)",
            "expected_lang": "hi",
            "script_validator": has_devanagari,
            "question": "कृत्रिम बुद्धिमत्ता किस विषय की शाखा है?",
        },
        {
            "name": "English Regression",
            "file": "english.txt",
            "lang": "English (en)",
            "expected_lang": "en",
            "script_validator": lambda t: "cloud computing" in t.lower() or "iaas" in t.lower(),
            "question": "What does Infrastructure as a Service (IaaS) offer?",
        },
    ]

    results = []

    print("\n" + "=" * 80)
    print("STARTING STEP 7 END-TO-END MULTILINGUAL PIPELINE VERIFICATION")
    print("=" * 80 + "\n")

    for idx, tc in enumerate(test_cases, 1):
        file_path = fixtures_dir / tc["file"]
        if not file_path.exists():
            print(f"[SKIP] Fixture {tc['file']} does not exist.")
            continue

        print(f"[{idx}/{len(test_cases)}] Testing {tc['name']} ({tc['file']})...")

        # 1. Upload file
        with open(file_path, "rb") as f:
            upload_res = client.post(
                "/api/upload",
                files={"file": (tc["file"], f, "application/octet-stream")}
            )

        if upload_res.status_code != 200:
            print(f"  [FAIL] Upload failed with status {upload_res.status_code}: {upload_res.text}")
            results.append({
                "lang": tc["lang"],
                "file": tc["file"],
                "chunks": 0,
                "script_ok": "No",
                "answered": "No",
                "quiz_count": 0,
                "status": "FAIL (Upload)"
            })
            continue

        upload_data = upload_res.json()
        doc_id = upload_data.get("document_id")

        # 2. Verify chunks and script
        content_res = client.get(f"/api/documents/{doc_id}/content")
        chunks = content_res.json().get("chunks", [])
        detected_lang = content_res.json().get("language", "en")
        warning = content_res.json().get("warning")

        all_text = " ".join(c.get("content", "") for c in chunks)
        script_ok = tc["script_validator"](all_text)

        # 3. Ask question in same language
        qa_res = client.post(
            "/api/qa",
            json={
                "query": tc["question"],
                "document_id": doc_id,
                "mode": "hybrid",
                "top_k": 3
            }
        )
        answer = qa_res.json().get("answer", "") if qa_res.status_code == 200 else ""
        citations = qa_res.json().get("citations", []) if qa_res.status_code == 200 else []
        answered = bool(answer and len(answer.strip()) > 10)

        # 4. Generate 5-question quiz
        quiz_res = client.post(
            "/api/quiz/generate",
            json={
                "document_id": doc_id,
                "num_questions": 5,
                "difficulty": "mixed"
            }
        )
        quiz_data = quiz_res.json() if quiz_res.status_code == 200 else {}
        quiz_questions = quiz_data.get("questions", [])
        quiz_count = len(quiz_questions)

        status_str = "PASS" if (len(chunks) > 0 and script_ok and answered and quiz_count > 0) else "PARTIAL"

        results.append({
            "lang": tc["lang"],
            "file": tc["file"],
            "chunks": len(chunks),
            "script_ok": "Yes" if script_ok else "No",
            "answered": "Yes" if answered else "No",
            "quiz_count": quiz_count,
            "status": status_str
        })

        print(f"  -> Chunks: {len(chunks)} | Script Verified: {script_ok} | Answered: {answered} | Quiz Count: {quiz_count} | Status: {status_str}")

    # Print ASCII results table
    print("\n" + "=" * 90)
    print("STEP 7 MULTILINGUAL PIPELINE VERIFICATION RESULTS TABLE")
    print("=" * 90)
    header = f"{'Language':<18} | {'File':<24} | {'Chunks':<6} | {'Script OK':<9} | {'Answered':<8} | {'Quiz Count':<10} | {'Status':<6}"
    print(header)
    print("-" * 90)
    for r in results:
        row = f"{r['lang']:<18} | {r['file']:<24} | {r['chunks']:<6} | {r['script_ok']:<9} | {r['answered']:<8} | {r['quiz_count']:<10} | {r['status']:<6}"
        print(row)
    print("=" * 90 + "\n")

    # Assert all passed
    for r in results:
        assert r["chunks"] > 0, f"Expected chunks for {r['file']}"
        assert r["script_ok"] == "Yes", f"Script verification failed for {r['file']}"
        assert r["answered"] == "Yes", f"Question answering failed for {r['file']}"
        assert r["quiz_count"] > 0, f"Quiz generation failed for {r['file']}"

    print("[SUCCESS] All multilingual document tests and English regression checks passed!\n")


if __name__ == "__main__":
    run_e2e_verification()
