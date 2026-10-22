import io
import json
import shutil
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime, timezone
from unittest.mock import Mock

import numpy as np
import pytest
from src.ai import budget, rag
from src.database.db import get_connection, init_db
from src.database.repository import DocumentRepository
from src.database.study import StudyRepository
from src.api import study, routes


def seed(ident='one'):
    repo = DocumentRepository()
    repo.insert_document_with_chunks(doc_id=ident, title=ident, filename=ident+'.txt', file_type='txt',
        file_size=100, doc_hash=ident, metadata={}, chunks=[{
        'id': ident+'-0', 'document_id': ident, 'chunk_index': 0, 'content': 'Rust focuses on memory safety and concurrency.',
        'token_count': 8, 'page_number': 2, 'embedding': np.array([1, 0], dtype=np.float32).tobytes()}])
    return repo


def question():
    return {'question': 'Which language focuses on memory safety?', 'correct_answer': 'Rust', 'topic': 'Languages',
        'options': [{'label': 'Rust', 'is_correct': True}, {'label': 'Ruby', 'is_correct': False},
                    {'label': 'R', 'is_correct': False}, {'label': 'Python', 'is_correct': False}],
        'source_chunk_id': '0', 'source_page': 2, 'source_quote': 'Rust focuses on memory safety and concurrency.'}


def test_subject_assignment_is_atomic_and_does_not_delete_documents(client):
    seed(); seed('two')
    subject = client.post('/api/subjects', json={'name': 'Operating Systems'}).json()['id']
    assert client.put(f'/api/subjects/{subject}/documents', json={'document_ids':['one','two']}).status_code == 200
    assert client.put(f'/api/subjects/{subject}/documents', json={'document_ids':['missing']}).status_code == 404
    assert client.get(f'/api/subjects/{subject}/documents').json()['document_ids'] == ['one','two']
    client.delete(f'/api/subjects/{subject}')
    assert len(client.get('/api/documents').json()['documents']) == 2


def test_streamed_chat_is_saved_and_followups_receive_history_and_exam_style(client, monkeypatch):
    repo = seed(); seed('two')
    contexts = repo.search_fts('Rust', filters={'document_ids':['one']})
    engine = Mock(search=Mock(return_value=contexts))
    monkeypatch.setattr(study, 'HybridSearchEngine', lambda: engine)
    prompts = []
    def stream(prompt):
        prompts.append(prompt)
        yield 'First point: Rust.'
        yield ' [Source 1]'
    monkeypatch.setattr(budget, 'stream', stream)
    body = {'document_id':'one', 'query':'Which language is discussed?', 'document_ids':['one','two'], 'answer_style':'6_marks'}
    response = client.post('/api/chat/stream', json=body)
    assert response.status_code == 200
    events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]
    ident = events[0]['session_id']
    assert [event['type'] for event in events] == ['session','delta','delta','done']
    assert '6-mark' in prompts[0]
    assert engine.search.call_args.kwargs['filters']['document_ids'] == ['one','two']
    body.update(session_id=ident, query='Explain the first point in simple language.', answer_style='simple')
    assert client.post('/api/chat/stream', json=body).status_code == 200
    assert 'First point: Rust.' in prompts[1]
    assert 'two minutes' in prompts[1]
    init_db()  # Reopening the same database preserves conversations.
    messages = client.get(f'/api/conversations/{ident}').json()['messages']
    assert [m['role'] for m in messages] == ['user','assistant','user','assistant']
    assert messages[-1]['citations'][0]['document_id'] == 'one'
    body['document_ids'] = ['one']
    assert client.post('/api/chat/stream', json=body).status_code == 409
    client.delete(f'/api/conversations/{ident}')
    assert client.get(f'/api/conversations/{ident}').status_code == 404


def test_failed_stream_never_persists_partial_answer(client, monkeypatch):
    seed()
    monkeypatch.setattr(study, 'HybridSearchEngine', lambda: Mock(search=Mock(return_value=[{'content':'Rust', 'document_id':'one'}])))
    def broken(prompt):
        yield 'partial'
        raise RuntimeError('Quota exhausted')
    monkeypatch.setattr(budget, 'stream', broken)
    response = client.post('/api/chat/stream', json={'document_id':'one','query':'Explain Rust'})
    events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]
    assert events[-1]['type'] == 'error'
    messages = StudyRepository().messages(events[0]['session_id'])
    assert len(messages) == 1 and messages[0]['role'] == 'user'


def test_quiz_scoring_history_weak_topics_and_revision_cards(client):
    seed(); repo = StudyRepository()
    ident = repo.save_quiz('one', [question()])
    # Prefix matching must never mark R as Rust.
    response = client.post('/api/study/attempts', json={'quiz_id':ident,'answers':{'0':'R'}})
    assert response.status_code == 200 and response.json()['correct'] == 0
    assert client.post('/api/study/attempts', json={'quiz_id':ident,'answers':{'0':'Rust'}}).json()['correct'] == 0
    progress = client.get('/api/documents/one/progress').json()
    assert progress['attempt_count'] == 1 and progress['topics'][0]['accuracy'] == 0
    assert client.post('/api/documents/one/flashcards/from-mistakes').json()['added'] == 1
    assert client.post('/api/documents/one/flashcards/from-mistakes').json()['added'] == 0
    card = client.get('/api/documents/one/flashcards?due_only=true').json()['cards'][0]
    revised = client.post(f"/api/flashcards/{card['id']}/review", json={'rating':'good'}).json()
    assert revised['interval_days'] == 1
    assert datetime.fromisoformat(revised['due_at']) > datetime.now(timezone.utc)
    assert client.get('/api/documents/one/flashcards?due_only=true').json()['cards'] == []
    assert client.post(f"/api/flashcards/{card['id']}/review", json={'rating':'invalid'}).status_code == 422


def test_invalid_or_incomplete_quiz_answers_are_rejected(client):
    seed(); ident = StudyRepository().save_quiz('one', [question()])
    assert client.post('/api/study/attempts', json={'quiz_id':ident,'answers':{}}).status_code == 422
    assert client.post('/api/study/attempts', json={'quiz_id':ident,'answers':{'0':'invented'}}).status_code == 422
    assert StudyRepository().progress('one')['attempt_count'] == 0


def test_retake_saves_a_separate_attempt_without_spending_ai_quota(client):
    seed(); repo = StudyRepository(); ident = repo.save_quiz('one', [question()])
    client.post('/api/study/attempts', json={'quiz_id':ident, 'answers':{'0':'Ruby'}})
    retake = client.post(f'/api/study/quizzes/{ident}/retake').json()['quiz_id']
    assert retake != ident and repo.quiz(retake)['questions'] == [question()]
    for _ in range(2):
        assert client.post('/api/study/attempts', json={'quiz_id':retake, 'answers':{'0':'Rust'}}).json()['correct'] == 1
    progress = repo.progress('one')
    assert progress['attempt_count'] == 2 and progress['correct'] == 1 and progress['total'] == 2
    assert client.post('/api/study/quizzes/missing/retake').status_code == 404


def test_notes_edits_preserve_older_versions_and_are_scoped_to_document(client):
    seed(); seed('two')
    original = {'sections':[{'number':1,'heading':'Original','content':'First explanation'}]}
    first = client.post('/api/documents/one/notes/versions', json={'notes':original, 'label':'Generated'}).json()['version_id']
    edited = {'sections':[{'number':1,'heading':'Edited','content':'My explanation'}]}
    second = client.post('/api/documents/one/notes/versions', json={'notes':edited}).json()['version_id']
    assert client.get(f'/api/documents/one/notes/versions/{first}').json()['notes'] == original
    assert client.get(f'/api/documents/one/notes/versions/{second}').json()['notes'] == edited
    assert client.get(f'/api/documents/two/notes/versions/{first}').status_code == 404
    assert len(client.get('/api/documents/one/notes/versions').json()['versions']) == 2


def clear_keys(monkeypatch):
    for provider in ['GEMINI','GROQ','OPENROUTER']:
        monkeypatch.delenv(provider+'_API_KEY', raising=False)
        monkeypatch.delenv(provider+'_FREE_TIER_CONFIRMED', raising=False)


def test_free_only_blocks_unconfirmed_cloud_accounts(monkeypatch):
    clear_keys(monkeypatch)
    monkeypatch.setenv('GEMINI_API_KEY','test')
    monkeypatch.setenv('GROQ_API_KEY','test')
    caller = Mock(side_effect=AssertionError('Unconfirmed account must not be called'))
    monkeypatch.setattr(rag, '_call_gemini_api', caller)
    monkeypatch.setattr(rag, '_call_groq_api', caller)
    assert rag.call_llm('test') is None
    caller.assert_not_called()


def test_budget_cache_and_quota_pause_without_paid_fallback(monkeypatch):
    clear_keys(monkeypatch)
    monkeypatch.setenv('GROQ_API_KEY','test')
    monkeypatch.setenv('GROQ_FREE_TIER_CONFIRMED','true')
    monkeypatch.setenv('GROQ_DAILY_LIMIT','1')
    caller = Mock(return_value='cached answer')
    monkeypatch.setattr(rag, '_call_groq_api', caller)
    assert rag.call_llm('same question') == 'cached answer'
    assert rag.call_llm('same question') == 'cached answer'
    assert rag.call_llm('different question') is None
    assert caller.call_count == 1
    status = budget.status()
    assert status['free_only'] and next(p for p in status['providers'] if p['provider']=='groq')['requests'] == 1


def test_budget_reservation_is_atomic_across_threads(monkeypatch):
    monkeypatch.setenv('GROQ_DAILY_LIMIT','3')
    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes = list(pool.map(lambda _: budget.reserve('groq'), range(20)))
    assert sum(outcomes) == 3


def test_openrouter_is_forced_to_free_router_even_if_other_model_is_configured(monkeypatch):
    monkeypatch.setenv('OPENROUTER_API_KEY','test')
    monkeypatch.setenv('OPENROUTER_MODEL','paid/model')
    model = next(p['model'] for p in budget.providers() if p['provider']=='openrouter')
    assert model == 'openrouter/free'
    request = budget.request_for('openrouter', model, 'question', True)
    assert json.loads(request.data)['model'] == 'openrouter/free'
    assert json.loads(request.data)['stream'] is True


def test_stream_yields_real_deltas_and_does_not_cache_incomplete_output(monkeypatch):
    clear_keys(monkeypatch); monkeypatch.setenv('OPENROUTER_API_KEY','test')
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def __iter__(self):
            yield b'data: {"choices":[{"delta":{"content":"first"}}]}\n'
            raise OSError('connection lost')
    monkeypatch.setattr(budget.urllib.request, 'urlopen', lambda *args, **kwargs: Response())
    iterator = budget.stream('question')
    assert next(iterator) == 'first'
    with pytest.raises(RuntimeError, match='connection.*interrupted'): next(iterator)
    assert budget.cached(budget.cache_key('openrouter','openrouter/free','question')) is None


def test_hashing_embeddings_remain_identical_after_restart():
    from src.ai.embeddings import EmbeddingEngine
    engines=[]
    for _ in range(2):
        engine=object.__new__(EmbeddingEngine); engine._setup_fallback(); engines.append(engine)
    a=engines[0].embed_texts(['Rust supports memory safety.', 'Python is dynamic.'])
    engines[0].embed_query('unrelated new query')
    b=engines[1].embed_texts(['Rust supports memory safety.', 'Python is dynamic.'])
    assert np.array_equal(a,b)


def test_truncated_provider_stream_is_not_cached_as_a_complete_answer(monkeypatch):
    clear_keys(monkeypatch); monkeypatch.setenv('OPENROUTER_API_KEY','test')
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def __iter__(self):
            yield b'data: {"choices":[{"delta":{"content":"cut short"},"finish_reason":"length"}]}\n'
            yield b'data: [DONE]\n'
    monkeypatch.setattr(budget.urllib.request, 'urlopen', lambda *args, **kwargs: Response())
    iterator = budget.stream('truncated question')
    assert next(iterator) == 'cut short'
    with pytest.raises(RuntimeError, match='output limit'): next(iterator)
    assert budget.cached(budget.cache_key('openrouter','openrouter/free','truncated question')) is None


def test_background_notes_are_saved_without_a_browser(client, monkeypatch):
    import time
    from src.ai import notes
    from src.ai.notes_jobs import NotesJobManager
    seed(); generated = {'sections':[{'number':1,'heading':'Memory safety','content':'Rust uses ownership.'}]}
    monkeypatch.setattr(notes, 'generate_hierarchical_notes', lambda **kwargs: {'notes':generated})
    manager = NotesJobManager()
    monkeypatch.setattr(NotesJobManager, '_instance', manager)
    response = client.post('/api/documents/one/notes?background=true')
    assert response.status_code == 200
    for _ in range(100):
        job = manager.get_job(response.json()['job_id'])
        if job['status'] in ('completed','failed'): break
        time.sleep(.01)
    assert job['status'] == 'completed'
    ident = job['result']['version_id']
    init_db()
    assert StudyRepository().note_version('one', ident) == generated


def test_native_pdf_upload_preview_highlight_and_cleanup(client, monkeypatch, tmp_path):
    import fitz
    from src.ingestion import ocr
    from src.ingestion.pipeline import IngestionPipeline
    original_dir = tmp_path/'originals'; original_dir.mkdir()
    monkeypatch.setattr(ocr, 'ORIGINALS_DIR', original_dir)
    fake=Mock(embed_texts=lambda texts:np.ones((len(texts),384), dtype=np.float32))
    monkeypatch.setattr(IngestionPipeline,'embedding_engine',property(lambda self:fake))
    with fitz.open() as pdf:
        page=pdf.new_page(); page.insert_text((60,80),'Solar panels convert sunlight into electricity using photovoltaic cells.')
        data=pdf.tobytes()
    uploaded=client.post('/api/upload', files={'file':('solar.pdf',data,'application/pdf')})
    assert uploaded.status_code == 200
    ident=uploaded.json()['document_id']
    preview=client.get(f'/api/documents/{ident}/pages/1',params={'excerpt':'Solar panels'})
    assert preview.status_code == 200 and preview.content.startswith(b'\x89PNG')
    assert preview.headers['x-evidence-highlighted'] == 'true'
    assert client.get(f'/api/documents/{ident}/original').content == data
    assert client.get(f'/api/documents/{ident}/pages/999').status_code == 422
    client.delete(f'/api/documents/{ident}')
    assert list(original_dir.iterdir()) == []


def test_scanned_pdf_uses_local_ocr(tmp_path):
    if not shutil.which('tesseract'):
        pytest.skip('Tesseract is optional; install it to exercise real OCR')
    import fitz
    from PIL import Image, ImageDraw, ImageFont
    from src.ingestion.parsers import DocumentParser
    image=Image.new('RGB',(1500,250),'white')
    font=ImageFont.truetype('DejaVuSans.ttf',35)
    ImageDraw.Draw(image).text((40,80),'SOLAR PANELS CONVERT SUNLIGHT INTO ELECTRICITY.',font=font,fill='black')
    buffer=io.BytesIO();image.save(buffer,format='PNG')
    path=tmp_path/'scan.pdf'
    with fitz.open() as pdf:
        page=pdf.new_page(width=750,height=125);page.insert_image(page.rect,stream=buffer.getvalue());pdf.save(path)
    pages,warning=DocumentParser.parse(str(path))
    assert 'SOLAR' in pages[0]['text'] and pages[0]['ocr_words']
