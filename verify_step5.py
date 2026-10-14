import time
import json
import functools
from fastapi.testclient import TestClient

print = functools.partial(print, flush=True)

from src.api.routes import app
from src.database.repository import DocumentRepository

client = TestClient(app)
repo = DocumentRepository()

def count_words_in_notes(notes):
    if not notes:
        return 0
    text = ""
    text += notes.get("title", "") + " "
    text += notes.get("subject", "") + " "
    text += notes.get("quote", "") + " "
    for sec in notes.get("sections", []):
        text += sec.get("heading", "") + " "
        text += sec.get("content", "") + " "
        for b in sec.get("bullets", []):
            text += b + " "
        kb = sec.get("keyBox") or {}
        for it in kb.get("items", []):
            text += it + " "
        text += sec.get("tip", "") + " "
    for t in notes.get("keyTakeaways", []):
        text += t + " "
    for r in notes.get("remember", []):
        text += r + " "
    for f in notes.get("formulas", []):
        text += f + " "
    return len([w for w in text.split() if w.strip()])

def run_step5_verification():
    print("=" * 80)
    print("STEP 5 - MULTI-DOCUMENT & MULTI-LANGUAGE VERIFICATION")
    print("=" * 80)

    docs = repo.get_all_documents()
    doc_10 = next((d for d in docs if "algorithms_10_pages" in d["filename"]), None)
    doc_100 = next((d for d in docs if "1.Introduction_Algorithm" in d["filename"]), None)
    doc_hindi = next((d for d in docs if "short-stories-in-hindi" in d["filename"] or "hindi" in d["filename"]), None)

    print(f"10-page doc: {doc_10['filename']} ({doc_10['id']})")
    print(f"100-page doc: {doc_100['filename']} ({doc_100['id']})")
    print(f"Hindi doc: {doc_hindi['filename']} ({doc_hindi['id']})")
    print("-" * 80)

    results = []

    # 1. 10-page Document
    print("\n[1/5] Generating notes for 10-page document (algorithms_10_pages.pdf)...")
    t0 = time.time()
    res10 = client.post(f"/api/documents/{doc_10['id']}/notes?detail_level=standard&language=en")
    t10 = time.time() - t0
    data10 = res10.json()
    notes10 = data10.get("notes", {})
    cov10 = notes10.get("coverage", {})
    words10 = count_words_in_notes(notes10)
    results.append({
        "name": doc_10["filename"][:24],
        "pages": f"{cov10.get('min_page', 1)}-{cov10.get('max_page', 10)}",
        "sections": f"{cov10.get('processed_sections', 0)}/{cov10.get('total_sections', 0)}",
        "words": words10,
        "time": f"{t10:.1f}s",
        "covered": cov10.get("coverage_text", "")[:35],
        "failed": len(cov10.get("failed_sections", [])),
    })

    # 2. 100-page Document / Biggest PDF
    print("\n[2/5] Generating notes for 100-page document (1.Introduction_Algorithm.pdf)...")
    t0 = time.time()
    res100 = client.post(f"/api/documents/{doc_100['id']}/notes?detail_level=standard&language=en")
    t100 = time.time() - t0
    data100 = res100.json()
    notes100 = data100.get("notes", {})
    cov100 = notes100.get("coverage", {})
    words100 = count_words_in_notes(notes100)
    results.append({
        "name": doc_100["filename"][:24],
        "pages": f"{cov100.get('min_page', 1)}-{cov100.get('max_page', 90)}",
        "sections": f"{cov100.get('processed_sections', 0)}/{cov100.get('total_sections', 0)}",
        "words": words100,
        "time": f"{t100:.1f}s",
        "covered": cov100.get("coverage_text", "")[:35],
        "failed": len(cov100.get("failed_sections", [])),
    })

    # 3. Hindi Document - Original (Hindi)
    print("\n[3/5] Generating Hindi notes in Original language...")
    t0 = time.time()
    res_hi = client.post(f"/api/documents/{doc_hindi['id']}/notes?detail_level=standard&language=original")
    t_hi = time.time() - t0
    data_hi = res_hi.json()
    notes_hi = data_hi.get("notes", {})
    cov_hi = notes_hi.get("coverage", {})
    words_hi = count_words_in_notes(notes_hi)
    results.append({
        "name": f"{doc_hindi['filename'][:16]} (Hindi)",
        "pages": f"{cov_hi.get('min_page', 1)}-{cov_hi.get('max_page', 85)}",
        "sections": f"{cov_hi.get('processed_sections', 0)}/{cov_hi.get('total_sections', 0)}",
        "words": words_hi,
        "time": f"{t_hi:.1f}s",
        "covered": cov_hi.get("coverage_text", "")[:35],
        "failed": len(cov_hi.get("failed_sections", [])),
    })

    # 4. Hindi Document - Both (Dual View)
    print("\n[4/5] Generating Hindi notes in Dual View ('both')...")
    t0 = time.time()
    res_dual = client.post(f"/api/documents/{doc_hindi['id']}/notes?detail_level=standard&language=both")
    t_dual = time.time() - t0
    data_dual = res_dual.json()
    notes_dual = data_dual.get("notes", {})
    cov_dual = notes_dual.get("coverage", {})
    dual_payload = notes_dual.get("dual_notes", {})
    has_dual = bool(dual_payload.get("original") and dual_payload.get("english"))
    words_dual = count_words_in_notes(dual_payload.get("original", {})) + count_words_in_notes(dual_payload.get("english", {}))
    results.append({
        "name": f"{doc_hindi['filename'][:16]} (Both)",
        "pages": f"{cov_dual.get('min_page', 1)}-{cov_dual.get('max_page', 85)}",
        "sections": f"{cov_dual.get('processed_sections', 0)}/{cov_dual.get('total_sections', 0)}",
        "words": words_dual,
        "time": f"{t_dual:.1f}s",
        "covered": "Dual View (Hindi & English)",
        "failed": len(cov_dual.get("failed_sections", [])),
    })

    # 5. Check other workspace features (Summarize, Chat, Quiz, Upload)
    print("\n[5/5] Confirming Summarize, Chat, Quiz, and Upload still work...")
    # Summarize
    res_sum = client.post(f"/api/documents/{doc_10['id']}/summarize")
    sum_ok = res_sum.status_code == 200 and bool(res_sum.json().get("answer"))
    print(f"  - Summarize: {'PASS (200)' if sum_ok else 'FAIL'}")

    # Chat / Query
    res_chat = client.post("/api/qa", json={"query": "What is an algorithm?", "document_id": doc_10["id"], "mode": "hybrid"})
    chat_ok = res_chat.status_code == 200 and bool(res_chat.json().get("answer"))
    print(f"  - Chat / Query: {'PASS (200)' if chat_ok else 'FAIL'}")

    # Quiz
    res_quiz = client.post("/api/quiz/generate", json={"document_id": doc_10["id"], "difficulty": "medium", "num_questions": 3})
    quiz_ok = res_quiz.status_code == 200 and bool(res_quiz.json().get("questions"))
    print(f"  - Quiz Generator: {'PASS (200)' if quiz_ok else 'FAIL'}")

    # Upload test
    test_content = b"This is a temporary test document to verify the upload feature remains fully functional."
    res_upload = client.post("/api/upload", files={"file": ("upload_verification_doc.txt", test_content, "text/plain")})
    upload_ok = res_upload.status_code == 200 and bool(res_upload.json().get("document_id"))
    print(f"  - Upload: {'PASS (200)' if upload_ok else 'FAIL'}")

    if upload_ok:
        try:
            repo.delete_document(res_upload.json()["document_id"])
        except Exception:
            pass

    # Print Results Table
    print("\n" + "=" * 95)
    print("RESULTS TABLE:")
    print("=" * 95)
    header = f"{'Document':<26} | {'Pages':<8} | {'Sections':<10} | {'Notes Words':<12} | {'Time':<8} | {'Failed':<8} | {'Coverage'}"
    print(header)
    print("-" * 95)
    for r in results:
        row = f"{r['name']:<26} | {r['pages']:<8} | {r['sections']:<10} | {r['words']:<12} | {r['time']:<8} | {r['failed']:<8} | {r['covered']}"
        print(row)
    print("=" * 95)

    # Scaling Check
    print("\nSCALING & MULTILINGUAL CHECKS:")
    print(f"  - 10-Page Notes Word Count: {words10} words")
    print(f"  - 100-Page Notes Word Count: {words100} words")
    is_scaling = words100 > words10
    print(f"  - Does 100-page document scale longer than 10-page doc? {'YES (Pass)' if is_scaling else 'NO'}")
    print(f"  - Can Hindi notes be shown in Hindi? {'YES (Pass)' if words_hi > 0 else 'NO'}")
    print(f"  - Can Hindi notes be shown in Both (Dual View)? {'YES (Pass)' if has_dual else 'NO'}")
    all_other_ok = sum_ok and chat_ok and quiz_ok and upload_ok
    print(f"  - Are Summarize, Chat, Quiz, and Upload working? {'YES (Pass)' if all_other_ok else 'NO'}")
    print("=" * 95)

if __name__ == "__main__":
    run_step5_verification()
