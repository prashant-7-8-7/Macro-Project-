import io
import json
import time
import urllib.error
from unittest.mock import Mock

import pytest

import check_ai
from src.ai import budget
from src.quiz.generator import _parse_quiz_response, _generate_single_batch
from src.quiz.schemas import QuizQuestion


CONTEXTS = [{'chunk_index': 0, 'page_number': 1, 'content': 'Rust focuses on memory safety and concurrency.'}]


def question():
    return QuizQuestion(question='Which language focuses on memory safety?',
        options=[{'label': label, 'is_correct': label == 'Rust'} for label in ['Rust', 'Python', 'Ruby', 'BASIC']],
        correct_answer='Rust', source_chunk_id='0', source_page=1,
        source_quote=CONTEXTS[0]['content'])


@pytest.fixture
def router(monkeypatch):
    for name in ('GEMINI', 'GROQ', 'OPENROUTER'):
        monkeypatch.delenv(name + '_API_KEY', raising=False)
        monkeypatch.delenv(name + '_FREE_TIER_CONFIRMED', raising=False)
    monkeypatch.setenv('OPENROUTER_API_KEY', 'private-test-key')
    monkeypatch.delenv('OPENROUTER_MODEL', raising=False)
    budget.clear_issue()


def body(data):
    return io.BytesIO(json.dumps(data).encode())


@pytest.mark.parametrize('model,expected', [
    ('meta-llama/llama-3.3-70b-instruct:free', 'meta-llama/llama-3.3-70b-instruct:free'),
    ('paid/model', 'openrouter/free'),
    ('openrouter/auto', 'openrouter/free'),
    ('meta-llama/model:free,paid/model', 'openrouter/free'),
])
def test_configurable_router_model_keeps_free_boundary(router, monkeypatch, model, expected):
    monkeypatch.setenv('OPENROUTER_MODEL', model)
    assert next(p['model'] for p in budget.providers() if p['provider'] == 'openrouter') == expected
    assert json.loads(budget.request_for('openrouter', model, 'question').data)['model'] == expected


def test_nonstream_output_limit_is_not_cached_or_sent_to_quiz_parser(router, monkeypatch):
    call = Mock(return_value=body({'choices': [{'message': {'content': '[{"question":'}, 'finish_reason': 'length'}]}))
    monkeypatch.setattr(budget.urllib.request, 'urlopen', call)
    assert budget.generate('quiz', {'openrouter': lambda p: budget.single_request('openrouter', p)}) is None
    assert 'output limit' in budget.last_issue_message()
    assert budget.cached(budget.cache_key('openrouter', 'openrouter/free', 'quiz')) is None


def test_accidental_key_whitespace_is_trimmed_for_authentication(router, monkeypatch):
    monkeypatch.setenv('OPENROUTER_API_KEY', '  private-test-key\n')
    request = budget.request_for('openrouter', 'openrouter/free', 'prompt')
    assert request.get_header('Authorization') == 'Bearer private-test-key'


def test_quiz_endpoint_surfaces_bad_key_after_one_attempt(client, router, monkeypatch):
    from src.api import routes
    from src.database.repository import DocumentRepository
    DocumentRepository().insert_document('doc', 'Test', 'doc.txt', 'txt', 10, 'quiz-auth', {})
    routes.app.dependency_overrides[routes.get_repo] = lambda: Mock(get_document_chunks_content=Mock(return_value=CONTEXTS))
    call = Mock(side_effect=urllib.error.HTTPError('https://openrouter.ai/api/v1/chat/completions', 401, 'rejected', {}, None))
    monkeypatch.setattr(budget.urllib.request, 'urlopen', call)
    result = client.post('/api/quiz/generate', json={'document_id': 'doc', 'num_questions': 10})
    assert result.status_code == 503
    assert 'openrouter' in result.json()['detail'] and 'rejected the API key' in result.json()['detail']
    assert call.call_count == 1


def test_quiz_endpoint_returns_source_checked_questions_from_complete_provider_json(client, router, monkeypatch):
    from src.api import routes
    from src.database.repository import DocumentRepository
    DocumentRepository().insert_document('doc', 'Test', 'doc.txt', 'txt', 10, 'quiz-valid', {})
    routes.app.dependency_overrides[routes.get_repo] = lambda: Mock(get_document_chunks_content=Mock(return_value=CONTEXTS))
    call = Mock(side_effect=lambda *a, **k: body({'choices': [{'message': {'content': json.dumps([question().model_dump()])}, 'finish_reason': 'stop'}]}))
    monkeypatch.setattr(budget.urllib.request, 'urlopen', call)
    result = client.post('/api/quiz/generate', json={'document_id': 'doc', 'num_questions': 1})
    assert result.status_code == 200 and result.json()['verified_count'] == 1
    assert result.json()['questions'][0]['source_quote'] == CONTEXTS[0]['content']


def test_invalid_cached_json_is_evicted_and_replaced_by_valid_complete_json(router, monkeypatch):
    key = budget.cache_key('openrouter', 'openrouter/free', 'quiz')
    budget.save_cache(key, '[{"question":')
    valid = json.dumps([question().model_dump()])
    call = Mock(return_value=valid)
    result = budget.generate('quiz', {'openrouter': call}, validator=lambda text: _parse_quiz_response(text) is not None)
    assert result == valid and budget.cached(key) == valid
    assert call.call_count == 1
    assert budget.last_issue_message() is None


def test_invalid_new_json_is_not_cached_and_explains_format_failure(router):
    assert budget.generate('quiz', {'openrouter': lambda p: 'Here is an unfinished ['},
                           validator=lambda text: _parse_quiz_response(text) is not None) is None
    assert 'invalid quiz' in budget.last_issue_message()
    assert budget.cached(budget.cache_key('openrouter', 'openrouter/free', 'quiz')) is None


def test_401_is_distinct_from_output_limit_and_403(router, monkeypatch):
    error = urllib.error.HTTPError('https://openrouter.ai/api/v1/chat/completions', 401, 'private-test-key', {}, None)
    monkeypatch.setattr(budget.urllib.request, 'urlopen', Mock(side_effect=error))
    assert budget.single_request('openrouter', 'prompt') is None
    assert 'rejected the API key' in budget.last_issue_message()
    assert 'private-test-key' not in budget.last_issue_message()
    assert budget.http_reason(403) == 'access'


def test_retry_after_is_respected_instead_of_fixed_hour_pause(router, monkeypatch):
    error = urllib.error.HTTPError('https://openrouter.ai/api/v1/chat/completions', 429, 'limit', {'Retry-After': '4'}, None)
    monkeypatch.setattr(budget.urllib.request, 'urlopen', Mock(side_effect=error))
    started = int(time.time())
    budget.generate('prompt', {'openrouter': lambda p: budget.single_request('openrouter', p)})
    status = next(p for p in budget.status()['providers'] if p['provider'] == 'openrouter')
    assert started + 4 <= status['blocked_until'] <= int(time.time()) + 4


def test_quiz_context_is_bounded_and_schema_validator_reaches_cache_layer(monkeypatch):
    from src.quiz import generator
    valid = json.dumps([question().model_dump()])
    call = Mock(return_value=valid)
    monkeypatch.setattr(generator, 'call_llm', call)
    contexts = [{**CONTEXTS[0], 'chunk_index': i, 'content': 'x' * 10000} for i in range(40)]
    assert _generate_single_batch(contexts, 3, 'easy', [], 0, 3)
    prompt = call.call_args.args[0]
    assert prompt.count('x') < 6100
    validator = call.call_args.kwargs['validator']
    assert validator(valid) and not validator('[{"question":')


@pytest.mark.parametrize('provider', ['openrouter', 'groq', 'gemini'])
def test_key_check_is_metadata_only_and_never_prints_key(monkeypatch, capsys, provider):
    monkeypatch.setenv(provider.upper() + '_API_KEY', 'private-test-key')
    monkeypatch.setattr(check_ai, 'load_dotenv', lambda *a: None)
    data = {'data': {'free_model_daily_requests': {'remaining': 45}}} if provider == 'openrouter' else {'data': []} if provider == 'groq' else {'models': []}
    call = Mock(return_value=body(data))
    monkeypatch.setattr(check_ai.urllib.request, 'urlopen', call)
    assert check_ai.main(['--provider', provider]) == 0
    request = call.call_args.args[0]
    assert request.get_method() == 'GET' and request.data is None
    assert request.full_url == check_ai.ENDPOINTS[provider]
    output = capsys.readouterr().out
    assert 'accepted' in output and 'private-test-key' not in output


def test_key_check_rejected_key_has_safe_replacement_instructions(monkeypatch, capsys):
    monkeypatch.setenv('OPENROUTER_API_KEY', 'private-test-key')
    monkeypatch.setattr(check_ai, 'load_dotenv', lambda *a: None)
    call = Mock(side_effect=urllib.error.HTTPError(check_ai.ENDPOINTS['openrouter'], 401, 'private-test-key', {}, None))
    monkeypatch.setattr(check_ai.urllib.request, 'urlopen', call)
    assert check_ai.main([]) == 1
    output = capsys.readouterr().out
    assert '401' in output and 'replacement key' in output and 'private-test-key' not in output


def test_missing_key_check_never_makes_a_network_request(monkeypatch):
    monkeypatch.delenv('OPENROUTER_API_KEY', raising=False)
    monkeypatch.setattr(check_ai, 'load_dotenv', lambda *a: None)
    call = Mock(side_effect=AssertionError('No key must mean no network request'))
    monkeypatch.setattr(check_ai.urllib.request, 'urlopen', call)
    assert check_ai.main([]) == 2
    call.assert_not_called()
