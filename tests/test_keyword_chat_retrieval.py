"""Natural-language questions and the built-in chips must retrieve real text."""
import json
from unittest.mock import Mock

import numpy as np
import pytest

from src.ai import budget, rag
from src.database.repository import DocumentRepository
from src.database.study import StudyRepository


LINK = 'The data link layer provides framing and node-to-node delivery.'
CRC = 'CRC detects transmission errors using a generator polynomial.'


def seed(ident='network', texts=None):
    texts = texts or [LINK, CRC]
    DocumentRepository().insert_document_with_chunks(
        doc_id=ident, title=ident, filename=ident + '.txt', file_type='txt',
        file_size=100, doc_hash=ident, metadata={}, chunks=[{
            'id': f'{ident}-{index}', 'document_id': ident, 'chunk_index': index,
            'content': text, 'token_count': 12, 'page_number': index + 1,
            'embedding': np.array([1, 0], dtype=np.float32).tobytes(),
        } for index, text in enumerate(texts)])


@pytest.fixture
def prompts(monkeypatch):
    result = []
    def stream(prompt):
        result.append(prompt)
        yield 'A grounded answer. [Source 1]'
    monkeypatch.setattr(budget, 'stream', stream)
    monkeypatch.setattr('src.retrieval.engine.EmbeddingEngine',
                        Mock(side_effect=AssertionError('Keyword mode must not load embeddings')))
    return result


def ask(client, query, session=None, document='network'):
    payload = {'document_id': document, 'query': query, 'mode': 'keyword', 'answer_style': '6_marks'}
    if session:
        payload['session_id'] = session
    response = client.post('/api/chat/stream', json=payload)
    assert response.status_code == 200
    return [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]


def context(prompt):
    return prompt.split('Context:\n', 1)[1].split('Previous conversation', 1)[0]


@pytest.mark.parametrize('query', [
    'what is data link layer',
    'What is the data link layer?',
    'Explain data link layer in simple language with an example.',
])
def test_natural_questions_retrieve_topic_without_matching_every_filler_word(client, prompts, query):
    seed()
    events = ask(client, query)
    assert events[-1]['type'] == 'done' and events[-1]['ai_available'] is True
    assert LINK in context(prompts[-1])
    assert events[-1]['citations'][0]['chunk_id'] == 'network-0'


def test_repeated_explain_simply_recovers_after_saved_no_context_answers(client, prompts):
    seed()
    repo = StudyRepository()
    session = repo.create_session('network', ['network'])['id']
    repo.add_message(session, 'user', 'what is data link layer')
    repo.add_message(session, 'assistant', rag.NO_CONTEXT_MESSAGES['en'])
    for _ in range(4):
        repo.add_message(session, 'user', 'Explain the most important concepts simply.')
        repo.add_message(session, 'assistant', rag.NO_CONTEXT_MESSAGES['en'])
    events = ask(client, 'Explain the most important concepts simply.', session)
    assert events[-1]['ai_available'] is True
    assert LINK in context(prompts[-1])
    assert rag.NO_CONTEXT_MESSAGES['en'] not in context(prompts[-1])


def test_new_topic_does_not_require_words_from_previous_question_or_answer(client, prompts):
    seed()
    events = ask(client, 'what is data link layer')
    events = ask(client, 'What is CRC?', events[0]['session_id'])
    assert events[-1]['ai_available'] is True
    assert CRC in context(prompts[-1])
    assert LINK not in context(prompts[-1])


@pytest.mark.parametrize('query', [
    'Explain the most important concepts simply.',
    'What are the key points in this document?',
    'Can you summarize the main findings?',
    'What are the main findings or conclusions?',
    'Explain it simply.',
])
def test_generic_chips_use_selected_document_excerpts_in_a_new_conversation(client, prompts, query):
    seed()
    seed('outside', ['Unselected private document.'])
    events = ask(client, query)
    assert events[-1]['ai_available'] is True
    assert LINK in context(prompts[-1]) and CRC in context(prompts[-1])
    assert 'Unselected private document' not in context(prompts[-1])
    assert {c['document_id'] for c in events[-1]['citations']} == {'network'}


def test_unknown_topic_does_not_silently_turn_into_document_overview(client, prompts):
    seed()
    events = ask(client, 'What is photosynthesis?')
    assert events[-1]['ai_available'] is False
    assert events[-1]['citations'] == []
    assert events[0]['has_context'] is False
    assert prompts == []


def test_complete_topic_matches_are_not_diluted_with_single_word_hits():
    seed(texts=[LINK, 'Data stores information.', 'A link is a connection.'])
    results = DocumentRepository().search_fts('What is the data link?', filters={'document_ids': ['network']})
    assert [r['id'] for r in results] == ['network-0']


def test_overview_redistributes_unused_slots_from_short_documents():
    seed('short', ['A short section.'])
    seed('long', [f'Long section {i}.' for i in range(20)])
    results = DocumentRepository().representative_chunks({'document_ids': ['short', 'long']}, top_k=6)
    assert len(results) == 6
    assert len({r['id'] for r in results}) == 6
    assert {r['document_id'] for r in results} == {'short', 'long'}


def test_relaxed_keyword_results_keep_document_scope_and_prefer_complete_topic():
    seed()
    seed('outside', [LINK + ' advantages disadvantages functions explanation'] * 8)
    repo = DocumentRepository()
    results = repo.search_fts('data link layer functions advantages', filters={'document_ids': ['network']})
    assert results and {r['document_id'] for r in results} == {'network'}
    assert repo.search_fts('" OR NOT NEAR() * ; --') == []


def test_document_overview_samples_beginning_middle_end_and_balances_documents():
    seed('network', [f'Network section {i}.' for i in range(21)])
    seed('other', [f'Other section {i}.' for i in range(21)])
    seed('outside', ['Must never enter selected document context.'])
    results = DocumentRepository().representative_chunks({'document_ids': ['network', 'other']}, top_k=6)
    assert len(results) == 6
    for ident in ('network', 'other'):
        assert {r['chunk_index'] for r in results if r['document_id'] == ident} == {0, 10, 20}
    assert DocumentRepository().representative_chunks({'document_ids': []}) == []
