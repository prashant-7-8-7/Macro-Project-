"""Persistent study features layered onto the existing document workflow."""
import asyncio
import json
from contextlib import closing
from typing import Literal
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse, FileResponse, Response
from pydantic import BaseModel, Field, StringConstraints
from typing import Annotated
from starlette.concurrency import run_in_threadpool
from src.database.repository import DocumentRepository
from src.database.study import StudyRepository
from src.database.db import get_connection
from src.ai import rag, budget
from src.ingestion.ocr import original_path, render_page
from src.retrieval.engine import HybridSearchEngine

router = APIRouter(prefix='/api')
Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]


def document_or_404(ident):
    document = DocumentRepository().get_document(ident)
    if not document:
        raise HTTPException(404, 'Document not found')
    return document


def resolve_scope(document_id, ids=None):
    scope = sorted(set(ids or [document_id]))
    if len(scope) > 20 or document_id not in scope:
        raise HTTPException(422, 'Select up to 20 documents including the open document')
    for ident in scope:
        document_or_404(ident)
    return scope


@router.get('/ai/usage')
def ai_usage():
    return budget.status()


class Subject(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]


class Documents(BaseModel):
    document_ids: list[str] = Field(default_factory=list, max_length=200)


@router.get('/subjects')
def subjects():
    return {'subjects': StudyRepository().collections()}


@router.post('/subjects')
def create_subject(payload: Subject):
    return StudyRepository().create_collection(payload.name)


@router.get('/subjects/{ident}/documents')
def subject_documents(ident: str):
    try:
        return {'document_ids': StudyRepository().collection_scope(ident)}
    except KeyError:
        raise HTTPException(404, 'Subject not found')


@router.put('/subjects/{ident}/documents')
def assign_subject(ident: str, payload: Documents):
    try:
        StudyRepository().assign_collection(ident, sorted(set(payload.document_ids)))
    except KeyError as exc:
        raise HTTPException(404, str(exc))
    return {'status': 'saved'}


@router.delete('/subjects/{ident}')
def remove_subject(ident: str):
    StudyRepository().delete_collection(ident)
    return {'status': 'deleted'}


@router.get('/documents/{doc_id}/conversations')
def conversations(doc_id: str):
    document_or_404(doc_id)
    return {'sessions': StudyRepository().sessions(doc_id)}


@router.get('/conversations/{ident}')
def conversation(ident: str):
    repo = StudyRepository()
    session = repo.session(ident)
    if not session:
        raise HTTPException(404, 'Conversation not found')
    return {'session': session, 'messages': repo.messages(ident)}


@router.delete('/conversations/{ident}')
def delete_conversation(ident: str):
    StudyRepository().delete_session(ident)
    return {'status': 'deleted'}


class ChatRequest(BaseModel):
    document_id: str
    document_ids: list[str] = Field(default_factory=list, max_length=20)
    query: Text
    session_id: str | None = None
    answer_style: Literal['general', 'simple', '2_marks', '6_marks', '10_marks', 'formulas'] = 'general'
    mode: Literal['hybrid', 'keyword', 'semantic'] = 'hybrid'


def prepare_chat(payload):
    scope = resolve_scope(payload.document_id, payload.document_ids)
    repo = StudyRepository()
    session = repo.session(payload.session_id) if payload.session_id else None
    if payload.session_id and not session:
        raise HTTPException(404, 'Conversation not found')
    if session and (session['document_id'] != payload.document_id or json.loads(session['scope_json']) != scope):
        raise HTTPException(409, 'Start a new conversation when changing selected documents')
    if not session:
        session = repo.create_session(payload.document_id, scope)
    history = repo.messages(session['id'])[-6:]
    previous = [m['content'] for m in history if m['role'] == 'user'][-1:]
    retrieval_query = payload.query
    if previous and len(payload.query) < 140:
        retrieval_query = previous[0] + '\nFollow-up: ' + payload.query
        if history and history[-1]['role'] == 'assistant':
            retrieval_query += '\n' + history[-1]['content'][:600]
    contexts = HybridSearchEngine().search(retrieval_query[:4000], top_k=6, mode=payload.mode, filters={'document_ids': scope})
    prepared = rag.prepare_answer(payload.query, contexts, history, payload.answer_style)
    return repo, session, prepared


@router.post('/chat/stream')
async def chat_stream(payload: ChatRequest, request: Request):
    repo, session, prepared = await run_in_threadpool(prepare_chat, payload)
    ident = session['id']
    def event(value):
        return 'data: ' + json.dumps(value, ensure_ascii=False) + '\n\n'
    async def events():
        iterator = None
        pieces = []
        await run_in_threadpool(repo.add_message, ident, 'user', payload.query)
        try:
            yield event({'type': 'session', 'session_id': ident})
            if not prepared.get('prompt'):
                pieces.append(prepared['answer'])
                yield event({'type': 'delta', 'text': prepared['answer']})
            else:
                iterator = budget.stream(prepared['prompt'])
                while True:
                    if await request.is_disconnected():
                        return
                    delta = await run_in_threadpool(next, iterator, None)
                    if delta is None:
                        break
                    pieces.append(delta)
                    yield event({'type': 'delta', 'text': delta})
            citations = prepared['citations']
            if await request.is_disconnected():
                return
            await run_in_threadpool(repo.add_message, ident, 'assistant', ''.join(pieces), citations)
            yield event({'type': 'done', 'citations': citations, 'ai_available': bool(prepared.get('prompt'))})
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            yield event({'type': 'error', 'message': str(exc) if isinstance(exc, RuntimeError) else 'Generation failed; check AI usage and server logs.'})
        finally:
            if iterator is not None:
                try:
                    iterator.close()
                except ValueError:
                    pass
    return StreamingResponse(events(), media_type='text/event-stream', headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})


class Attempt(BaseModel):
    quiz_id: str
    answers: dict[str, str]


@router.post('/study/quizzes/{ident}/retake')
def retake_quiz(ident: str):
    repo = StudyRepository()
    try:
        quiz = repo.quiz(ident)
    except KeyError:
        raise HTTPException(404, 'Quiz not found')
    return {'quiz_id': repo.save_quiz(quiz['document_id'], quiz['questions'])}


@router.post('/study/attempts')
def save_attempt(payload: Attempt):
    try:
        return StudyRepository().save_attempt(payload.quiz_id, payload.answers)
    except KeyError:
        raise HTTPException(404, 'Quiz not found')
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@router.get('/documents/{doc_id}/progress')
def progress(doc_id: str):
    document_or_404(doc_id)
    return StudyRepository().progress(doc_id)


@router.post('/documents/{doc_id}/flashcards/from-mistakes')
def cards_from_mistakes(doc_id: str):
    document_or_404(doc_id)
    repo = StudyRepository()
    return {'added': repo.add_flashcards(doc_id, repo.progress(doc_id)['wrong_questions'])}


class CardCount(BaseModel):
    count: int = Field(default=8, ge=1, le=20)


@router.post('/documents/{doc_id}/flashcards/generate')
def generate_cards(doc_id: str, payload: CardCount):
    document_or_404(doc_id)
    from src.quiz.generator import generate_questions
    from src.quiz.validator import validate_questions
    chunks = DocumentRepository().get_document_chunks_content(doc_id)
    questions = generate_questions(chunks, payload.count, 'mixed')
    checked, _ = validate_questions(questions, chunks)
    return {'added': StudyRepository().add_flashcards(doc_id, [q.model_dump() for q in checked[:payload.count]]),
            'message': 'Only source-checked cards are saved. Check AI usage if none could be generated.'}


@router.get('/documents/{doc_id}/flashcards')
def flashcards(doc_id: str, due_only: bool = False):
    document_or_404(doc_id)
    return {'cards': StudyRepository().flashcards(doc_id, due_only)}


class Review(BaseModel):
    rating: Literal['again', 'hard', 'good', 'easy']


@router.post('/flashcards/{ident}/review')
def review(ident: str, payload: Review):
    try:
        return StudyRepository().review_flashcard(ident, payload.rating)
    except KeyError:
        raise HTTPException(404, 'Flashcard not found')


class NotesVersion(BaseModel):
    notes: dict
    label: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)] = 'Edited notes'


@router.post('/documents/{doc_id}/notes/versions')
def save_notes(doc_id: str, payload: NotesVersion):
    document_or_404(doc_id)
    if len(json.dumps(payload.notes)) > 1_000_000:
        raise HTTPException(413, 'Notes version is too large')
    if not isinstance(payload.notes.get('sections'), list):
        raise HTTPException(422, 'Notes must contain a section list')
    return {'version_id': StudyRepository().save_notes(doc_id, payload.notes, payload.label)}


@router.get('/documents/{doc_id}/notes/versions')
def note_versions(doc_id: str):
    document_or_404(doc_id)
    return {'versions': StudyRepository().note_versions(doc_id)}


@router.get('/documents/{doc_id}/notes/versions/{ident}')
def note_version(doc_id: str, ident: str):
    document_or_404(doc_id)
    try:
        return {'notes': StudyRepository().note_version(doc_id, ident)}
    except KeyError:
        raise HTTPException(404, 'Notes version not found')


@router.get('/documents/{doc_id}/original')
def original(doc_id: str):
    document = document_or_404(doc_id)
    path = original_path(document)
    if not path.is_file():
        raise HTTPException(404, 'Reupload the document to enable original-page preview')
    return FileResponse(path, filename=document['filename'], content_disposition_type='inline')


@router.get('/documents/{doc_id}/pages/{page_number}')
def page(doc_id: str, page_number: int, excerpt: str = ''):
    document = document_or_404(doc_id)
    if document['file_type'] != 'pdf':
        raise HTTPException(415, 'Page preview is available for PDFs')
    path = original_path(document)
    if not path.is_file():
        raise HTTPException(404, 'Reupload this PDF to enable original-page preview')
    with closing(get_connection()) as db:
        row = db.execute('SELECT words_json FROM document_ocr WHERE document_id=? AND page_number=?', (doc_id, page_number)).fetchone()
    try:
        png, count, highlighted = render_page(path, page_number, excerpt[:350], json.loads(row[0]) if row else None)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    return Response(png, media_type='image/png', headers={'X-Page-Count': str(count), 'X-Evidence-Highlighted': str(highlighted).lower()})
