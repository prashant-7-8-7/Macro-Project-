"""Protocol regressions for provider failures after HTTP 200 headers."""
import io
import json
from unittest.mock import Mock

import pytest

from src.ai import budget
from src.database.repository import DocumentRepository


@pytest.fixture
def openrouter(monkeypatch):
    for provider in ('GEMINI', 'GROQ', 'OPENROUTER'):
        monkeypatch.delenv(provider + '_API_KEY', raising=False)
        monkeypatch.delenv(provider + '_FREE_TIER_CONFIRMED', raising=False)
    monkeypatch.setenv('OPENROUTER_API_KEY', 'private-test-key')


def response(*events):
    return io.BytesIO(b''.join(
        b'data: ' + (event if isinstance(event, str) else json.dumps(event)).encode() + b'\n\n'
        for event in events))


@pytest.mark.parametrize('finish,message', [
    ('length', 'output limit'),
    ('content_filter', 'content filter'),
    ('error', 'provider returned an error'),
])
def test_failed_finish_is_reported_without_caching_or_retrying(openrouter, monkeypatch, finish, message):
    call = Mock(return_value=response(
        {'choices': [{'delta': {'content': '**Partial**'}, 'finish_reason': finish}]}, '[DONE]'))
    monkeypatch.setattr(budget.urllib.request, 'urlopen', call)
    iterator = budget.stream('explain the layer')
    assert next(iterator) == '**Partial**'
    with pytest.raises(RuntimeError, match=message) as error:
        next(iterator)
    assert 'partial answer was not saved' in str(error.value)
    assert budget.cached(budget.cache_key('openrouter', 'openrouter/free', 'explain the layer')) is None
    assert call.call_count == 1


def test_midstream_quota_error_blocks_provider_and_keeps_secrets_out_of_logs(openrouter, monkeypatch, caplog):
    call = Mock(return_value=response(
        {'choices': [{'delta': {'content': 'First point.'}}]},
        {'error': {'code': 429, 'message': 'private-test-key private document text'},
         'choices': [{'delta': {}, 'finish_reason': 'error'}]}, '[DONE]'))
    monkeypatch.setattr(budget.urllib.request, 'urlopen', call)
    iterator = budget.stream('private document text')
    assert next(iterator) == 'First point.'
    with pytest.raises(RuntimeError, match='rate or quota limit'):
        next(iterator)
    status = next(p for p in budget.status()['providers'] if p['provider'] == 'openrouter')
    assert status['blocked_until'] > 0
    assert budget.reserve('openrouter') is False
    assert 'quota' in caplog.text
    assert 'private-test-key' not in caplog.text
    assert 'private document text' not in caplog.text
    assert call.call_count == 1


def test_empty_length_response_is_not_misreported_as_missing_quota(openrouter, monkeypatch):
    monkeypatch.setattr(budget.urllib.request, 'urlopen', lambda *a, **k: response(
        {'choices': [{'delta': {}, 'finish_reason': 'length'}]}, '[DONE]'))
    with pytest.raises(RuntimeError, match='output limit'):
        list(budget.stream('question'))


def test_completed_stream_is_cached_without_spending_another_request(openrouter, monkeypatch):
    call = Mock(return_value=response(
        {'choices': [{'delta': {'content': 'A complete answer.'}}]},
        {'choices': [{'delta': {}, 'finish_reason': 'stop'}]}, '[DONE]'))
    monkeypatch.setattr(budget.urllib.request, 'urlopen', call)
    assert ''.join(budget.stream('question')) == 'A complete answer.'
    assert ''.join(budget.stream('question')) == 'A complete answer.'
    assert call.call_count == 1
    assert next(p for p in budget.status()['providers'] if p['provider'] == 'openrouter')['requests'] == 1


def test_timeout_has_actionable_message_without_caching(openrouter, monkeypatch):
    monkeypatch.setattr(budget.urllib.request, 'urlopen', Mock(side_effect=TimeoutError()))
    with pytest.raises(RuntimeError, match='timed out'):
        list(budget.stream('question'))
    assert budget.cached(budget.cache_key('openrouter', 'openrouter/free', 'question')) is None


def test_keyword_chat_bypasses_embedding_model_and_still_saves_answer(client, monkeypatch):
    from src.ai.vector_math import serialize_embedding
    import numpy as np
    repo = DocumentRepository()
    repo.insert_document_with_chunks(doc_id='doc', title='Layer', filename='layer.txt', file_type='txt',
        file_size=100, doc_hash='layer', metadata={}, chunks=[{
            'id': 'chunk', 'document_id': 'doc', 'chunk_index': 0,
            'content': 'The data link layer uses frames.', 'token_count': 8, 'page_number': 1,
            'embedding': serialize_embedding(np.array([1, 0], dtype=np.float32))}])
    model = Mock(side_effect=AssertionError('Keyword chat must skip embeddings'))
    monkeypatch.setattr('src.retrieval.engine.EmbeddingEngine', model)
    def stream(prompt):
        yield 'The layer uses frames. [Source 1]'
    monkeypatch.setattr(budget, 'stream', stream)
    result = client.post('/api/chat/stream', json={'document_id': 'doc', 'query': 'frames', 'mode': 'keyword'})
    events = [json.loads(line[6:]) for line in result.text.splitlines() if line.startswith('data: ')]
    assert events[-1]['type'] == 'done'
    assert events[-1]['citations'][0]['document_id'] == 'doc'
    model.assert_not_called()
    messages = client.get('/api/conversations/' + events[0]['session_id']).json()['messages']
    assert messages[-1]['role'] == 'assistant'


@pytest.mark.parametrize('value,expected', [('8192', 8192), ('999999', 16384), ('1', 256)])
def test_output_limit_is_configurable_and_bounded(monkeypatch, value, expected):
    monkeypatch.setenv('AI_MAX_OUTPUT_TOKENS', value)
    for provider in ('groq', 'openrouter', 'gemini'):
        payload = json.loads(budget.request_for(provider, 'model', 'question', True).data)
        actual = payload['generationConfig']['maxOutputTokens'] if provider == 'gemini' else payload['max_tokens']
        assert actual == expected
