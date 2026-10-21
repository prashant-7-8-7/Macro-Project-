import json
import threading
import time
from unittest.mock import Mock

import pytest

from src.ai import rag, notes
from src.ai.notes_jobs import NotesJobManager, NotesQueueFull
from src.api import routes
from src.quiz.generator import _sample_contexts_for_batch, generate_questions
from src.quiz.schemas import QuizQuestion, QuizOption
from src.quiz.validator import validate_question


def question(answer="Rust", **updates):
    values = dict(question="Which language focuses on memory safety?",
                  options=[QuizOption(label=answer, is_correct=True)] +
                          [QuizOption(label=label, is_correct=False) for label in ["Python", "BASIC", "Fortran"]],
                  correct_answer=answer, source_chunk_id="0", source_page=999)
    values.update(updates)
    return QuizQuestion(**values)


CONTEXTS = [{"chunk_index": 0, "page_number": 1, "content": "Python is a high-level programming language."},
            {"chunk_index": 1, "page_number": 5, "content": "Rust focuses on memory safety and concurrency."}]


def test_quiz_batches_rotate_coverage_and_include_both_document_ends():
    contexts = [{"chunk_index": i} for i in range(100)]
    batches = [_sample_contexts_for_batch(contexts, i, 4) for i in range(4)]
    sampled_sets = [{ctx["chunk_index"] for ctx in batch} for batch in batches]
    assert all(len(batch) == 25 for batch in batches)
    assert all({0, 99} <= batch for batch in sampled_sets)
    assert len(set.union(*sampled_sets)) > 75


def test_correct_answer_repairs_wrong_citation_and_page():
    result = validate_question(question(source_quote="Rust focuses on memory safety and concurrency."), CONTEXTS)
    assert result.status == "verified"
    assert result.source_chunk_id == "1"
    assert result.source_page == 5


def test_existing_chunk_id_does_not_verify_an_invented_answer():
    result = validate_question(question(answer="Java"), CONTEXTS)
    assert result.status == "rejected"
    assert result.grounding_score == 0


def test_fabricated_supporting_quote_is_rejected():
    result = validate_question(question(source_chunk_id="1", source_quote="Rust is the fastest language in the world."), CONTEXTS)
    assert result.status == "rejected"


def test_partial_word_does_not_count_as_answer_evidence():
    result = validate_question(question(), [{"chunk_index": 0, "page_number": 1,
        "content": "Trust focuses on memory safety, according to this fictional example."}])
    assert result.status == "rejected"


@pytest.mark.parametrize("content,status", [
    ("The valid numerical range is 2 to 5.", "rejected"),
    ("The valid numerical range is 1-2.", "verified"),
])
def test_numeric_ranges_are_checked_as_complete_answers(content, status):
    result = validate_question(question(answer="1-2", question="What is the valid numerical range?"),
                               [{"chunk_index": 0, "page_number": 1, "content": content}])
    assert result.status == status


def test_answer_and_quote_must_come_from_the_same_chunk():
    result = validate_question(question(source_quote="Python is a high-level programming language."), CONTEXTS)
    assert result.status == "rejected"


def test_quiz_generation_excludes_questions_seen_in_previous_attempts(monkeypatch):
    batch = Mock(return_value=[question(), question(question="Which Rust feature improves memory safety?")])
    monkeypatch.setattr("src.quiz.generator._generate_single_batch", batch)
    result = generate_questions(CONTEXTS, num_questions=1, existing_questions=[question().question], batch_offset=2)
    assert len(result) == 1
    assert result[0].question != question().question
    assert question().question in batch.call_args.kwargs["existing_questions"]
    assert batch.call_args.kwargs["batch_idx"] == 2


def test_existing_quiz_api_returns_checked_source_excerpt(client, monkeypatch):
    from src.quiz import generator
    from src.database.repository import DocumentRepository
    DocumentRepository().insert_document('doc', 'Test', 'doc.txt', 'txt', 10, 'test-quiz-document', {})
    repo = Mock(get_document_chunks_content=Mock(return_value=CONTEXTS))
    routes.app.dependency_overrides[routes.get_repo] = lambda: repo
    generated = question(source_quote="Rust focuses on memory safety and concurrency.").model_dump()
    llm = Mock(return_value=json.dumps([generated]))
    monkeypatch.setattr(generator, "call_llm", llm)
    response = client.post("/api/quiz/generate", json={"document_id": "doc", "num_questions": 1})
    assert response.status_code == 200
    result = response.json()
    assert result["verified_count"] == 1
    assert result["questions"][0]["source_chunk_id"] == "1"
    assert result["questions"][0]["source_page"] == 5
    assert result["questions"][0]["source_quote"] == generated["source_quote"]
    assert '"source_quote"' in llm.call_args.args[0]


def test_cloud_workflow_keeps_gemini_to_groq_fallback_with_own_keys(monkeypatch):
    monkeypatch.setenv('GEMINI_FREE_TIER_CONFIRMED', 'true')
    monkeypatch.setenv('GROQ_FREE_TIER_CONFIRMED', 'true')
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-test")
    monkeypatch.setenv("GROQ_API_KEY", "groq-test")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    gemini = Mock(return_value=None)
    groq = Mock(return_value="answer")
    monkeypatch.setattr(rag, "_call_gemini_api", gemini)
    monkeypatch.setattr(rag, "_call_groq_api", groq)
    monkeypatch.setattr(rag.urllib.request, "urlopen", Mock(side_effect=AssertionError("Unexpected provider")))
    assert rag.call_llm("question") == "answer"
    gemini.assert_called_once_with("gemini-test", "question")
    groq.assert_called_once_with("groq-test", "question")


def test_gemini_failure_never_sends_its_key_to_openrouter(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-test")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setattr(rag, "_call_gemini_api", Mock(return_value=None))
    request = Mock(side_effect=AssertionError("Credential crossed providers"))
    monkeypatch.setattr(rag.urllib.request, "urlopen", request)
    assert rag.call_llm("question") is None
    request.assert_not_called()


def test_openrouter_fallback_uses_only_openrouter_key(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-test")
    monkeypatch.setenv("OPENROUTER_API_KEY", "router-test")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setattr(rag, "_call_gemini_api", Mock(return_value=None))
    response = Mock()
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    response.read.return_value = json.dumps({"choices": [{"message": {"content": "answer"}}]}).encode()
    request = Mock(return_value=response)
    monkeypatch.setattr(rag.urllib.request, "urlopen", request)
    assert rag.call_llm("question") == "answer"
    assert request.call_args.args[0].get_header("Authorization") == "Bearer router-test"


def test_unavailable_ai_does_not_report_a_successful_response(monkeypatch):
    monkeypatch.setattr(rag, "call_llm", Mock(return_value=None))
    response = rag.synthesize_answer("Which language is described?", CONTEXTS)
    assert response["ai_available"] is False
    assert response["citations"]


def wait_for_jobs(manager, *ids):
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        if all(manager.get_job(job_id)["status"] in {"completed", "failed"} for job_id in ids):
            break
        time.sleep(0.01)
    assert all(manager.get_job(job_id)["status"] == "completed" for job_id in ids)


def test_duplicate_notes_requests_reuse_job_and_concurrency_is_bounded(monkeypatch):
    started, release = threading.Event(), threading.Event()
    def generation(**kwargs):
        started.set()
        assert release.wait(3)
        return {"notes": {"sections": []}}
    generation_mock = Mock(side_effect=generation)
    monkeypatch.setattr(notes, "generate_hierarchical_notes", generation_mock)
    manager = NotesJobManager(max_concurrent=1)
    first = manager.create_job("doc", "Title", CONTEXTS)
    second = None
    try:
        assert started.wait(2)
        assert manager.create_job("doc", "Title", CONTEXTS) == first
        second = manager.create_job("doc", "Title", CONTEXTS, notes_language="hi")
        assert manager.get_job(second)["status"] == "pending"
        assert generation_mock.call_count == 1
    finally:
        release.set()
    wait_for_jobs(manager, first, second)
    assert generation_mock.call_count == 2


def test_notes_job_capacity_fails_cleanly_without_starting_more_workers(monkeypatch):
    started, release = threading.Event(), threading.Event()
    def generation(**kwargs):
        started.set()
        assert release.wait(3)
        return {"notes": {"sections": []}}
    monkeypatch.setattr(notes, "generate_hierarchical_notes", generation)
    manager = NotesJobManager(max_concurrent=1, max_pending=1)
    first = manager.create_job("doc", "Title", CONTEXTS)
    try:
        assert started.wait(2)
        with pytest.raises(NotesQueueFull):
            manager.create_job("other", "Title", CONTEXTS)
        assert manager.create_job("doc", "Title", CONTEXTS) == first
    finally:
        release.set()
    wait_for_jobs(manager, first)


def test_notes_endpoint_reports_queue_capacity_as_retryable(client, monkeypatch):
    repo = Mock(get_document_chunks_content=Mock(return_value=CONTEXTS),
                get_all_documents=Mock(return_value=[{"id": "doc", "filename": "doc.txt", "language": "en"}]))
    routes.app.dependency_overrides[routes.get_repo] = lambda: repo
    manager = Mock(create_job=Mock(side_effect=NotesQueueFull("Please retry later")))
    monkeypatch.setattr(NotesJobManager, "get_instance", classmethod(lambda cls: manager))
    response = client.post("/api/documents/doc/notes?background=true")
    assert response.status_code == 429
    assert response.headers["retry-after"] == "15"
