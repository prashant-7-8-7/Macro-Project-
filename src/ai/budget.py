"""Free-tier safeguards, local request budgets, caching, and streaming HTTP adapters."""
import hashlib
import json
import logging
import os
import re
import time
import urllib.error
import urllib.request
from contextlib import closing
from contextvars import ContextVar
from datetime import datetime, timezone
from src.database.db import get_connection

logger = logging.getLogger(__name__)
_last_issue = ContextVar('ai_last_issue', default=None)


def clear_issue():
    _last_issue.set(None)


def record_issue(provider, reason):
    _last_issue.set((provider, reason))
    logger.warning('%s generation unavailable (%s)', provider, reason)


def last_issue_message():
    issue = _last_issue.get()
    return f'{issue[0]}: {stream_failure(issue[1])}' if issue else None


def free_openrouter_model(model):
    # The catalog's :free variant is required, never a paid fallback array.
    model = (model or '').strip()
    return model if model == 'openrouter/free' or re.fullmatch(r'[\w.-]+/[\w.-]+:free', model) else 'openrouter/free'


def http_reason(code):
    return {401: 'auth', 402: 'credits', 403: 'access', 404: 'model', 429: 'quota'}.get(code, 'provider_error')


def pause_after_limit(provider, headers=None):
    try:
        seconds = max(1, min(86400, int((headers or {}).get('Retry-After', '60'))))
    except (ValueError, TypeError):
        seconds = 60
    block(provider, seconds)


def providers():
    result = []
    for name, default in [('gemini', 'gemini-3.8-flash'), ('groq', 'qwen/qwen3.8-27b'), ('openrouter', 'openrouter/free')]:
        key = os.environ.get(name.upper() + '_API_KEY', '').strip()
        model = os.environ.get(name.upper() + '_MODEL', default)
        if name == 'openrouter':
            model = free_openrouter_model(model)
        confirmed = name == 'openrouter' or os.environ.get(name.upper() + '_FREE_TIER_CONFIRMED', '').lower() == 'true'
        result.append({'provider': name, 'model': model, 'configured': bool(key), 'confirmed_free': confirmed})
    return result


def today():
    return datetime.now(timezone.utc).date().isoformat()


def reserve(provider):
    limits = {'gemini': 20, 'groq': 50, 'openrouter': 40}
    limit = int(os.environ.get(provider.upper() + '_DAILY_LIMIT', str(limits[provider])))
    with closing(get_connection()) as db, db:
        db.execute('BEGIN IMMEDIATE')
        db.execute('INSERT OR IGNORE INTO ai_daily_usage(provider,day) VALUES (?,?)', (provider, today()))
        row = db.execute('SELECT * FROM ai_daily_usage WHERE provider=? AND day=?', (provider, today())).fetchone()
        if row['requests'] >= limit or row['blocked_until'] > int(time.time()):
            return False
        db.execute('UPDATE ai_daily_usage SET requests=requests+1 WHERE provider=? AND day=?', (provider, today()))
        return True


def block(provider, seconds=3600):
    with closing(get_connection()) as db, db:
        db.execute('UPDATE ai_daily_usage SET blocked_until=? WHERE provider=? AND day=?',
                   (int(time.time()) + seconds, provider, today()))


def status():
    rows = providers()
    with closing(get_connection()) as db:
        usage = {r['provider']: dict(r) for r in db.execute('SELECT * FROM ai_daily_usage WHERE day=?', (today(),))}
    for row in rows:
        row.update(usage.get(row['provider'], {'requests': 0, 'blocked_until': 0}))
        row['daily_limit'] = int(os.environ.get(row['provider'].upper() + '_DAILY_LIMIT', {'gemini':'20','groq':'50','openrouter':'40'}[row['provider']]))
    return {'free_only': True, 'providers': rows,
            'message': 'Only confirmed free-tier accounts are used. Account billing must be verified in the provider console; this app cannot inspect it.'}


def cache_key(provider, model, prompt):
    credential = os.environ.get(provider.upper() + '_API_KEY', '').strip()
    return hashlib.sha256((provider + model + credential + prompt).encode()).hexdigest()


def cached(key):
    with closing(get_connection()) as db:
        row = db.execute('SELECT response FROM ai_response_cache WHERE cache_key=? AND created_at>?',
                         (key, int(time.time()) - 30 * 86400)).fetchone()
        return row[0] if row else None


def save_cache(key, text):
    if not text.strip():
        return
    with closing(get_connection()) as db, db:
        db.execute('INSERT OR REPLACE INTO ai_response_cache VALUES (?,?,?)', (key, text, int(time.time())))
        db.execute('DELETE FROM ai_response_cache WHERE created_at<?', (int(time.time()) - 30 * 86400,))


def request_for(provider, model, prompt, stream=False):
    if provider == 'openrouter':
        model = free_openrouter_model(model)
    key = os.environ.get(provider.upper() + '_API_KEY', '').strip()
    headers = {'Content-Type': 'application/json'}
    max_tokens = max(256, min(16384, int(os.environ.get('AI_MAX_OUTPUT_TOKENS', '4096'))))
    if provider == 'gemini':
        action = 'streamGenerateContent?alt=sse' if stream else 'generateContent'
        url = f'https://generativelanguage.googleapis.com/v1beta/models/{model}:{action}'
        headers['x-goog-api-key'] = key
        payload = {'contents': [{'parts': [{'text': prompt}]}], 'generationConfig': {'maxOutputTokens': max_tokens}}
    else:
        url = 'https://api.groq.com/openai/v1/chat/completions' if provider == 'groq' else 'https://openrouter.ai/api/v1/chat/completions'
        headers['Authorization'] = 'Bearer ' + key
        payload = {'model': model, 'messages': [{'role': 'user', 'content': prompt}],
                   'temperature': 0.3, 'max_tokens': max_tokens, 'stream': stream}
        if provider == 'groq' and model in ('qwen/qwen3.8-27b', 'qwen/qwen3.6-27b'):
            payload['reasoning_effort'] = 'none'
    return urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers, method='POST')


def read_text(provider, data, stream=False):
    if provider == 'gemini':
        return ''.join(p.get('text', '') for c in data.get('candidates', [])[:1] for p in c.get('content', {}).get('parts', []))
    choices = data.get('choices', [])
    return (choices[0].get('delta' if stream else 'message', {}).get('content') or '') if choices else ''


def single_request(provider, prompt):
    model = next(p['model'] for p in providers() if p['provider'] == provider)
    try:
        with urllib.request.urlopen(request_for(provider, model, prompt), timeout=60) as response:
            data = json.load(response)
            if data.get('error'):
                error = data['error']
                code = error.get('code') if isinstance(error, dict) else None
                reason = http_reason(int(code)) if str(code).isdigit() else 'provider_error'
                if reason == 'quota':
                    pause_after_limit(provider, getattr(response, 'headers', None))
                record_issue(provider, reason)
                return None
            choices = data.get('candidates', []) if provider == 'gemini' else data.get('choices', [])
            finish = next((c.get('finish_reason') or c.get('finishReason') for c in choices
                           if c.get('finish_reason') or c.get('finishReason')), None)
            if finish not in (None, 'stop', 'STOP'):
                record_issue(provider, 'length' if finish in ('length', 'MAX_TOKENS') else 'provider_error')
                return None
            text = read_text(provider, data).strip()
            if not text:
                record_issue(provider, 'incomplete')
            return text or None
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            pause_after_limit(provider, exc.headers)
        record_issue(provider, http_reason(exc.code))
        logger.warning('%s request failed with HTTP %s', provider, exc.code)
    except Exception as exc:
        record_issue(provider, 'timeout' if isinstance(exc, TimeoutError) else 'provider_error')
        logger.warning('%s request unavailable (%s)', provider, type(exc).__name__)
    return None


def generate(prompt, callers, validator=None):
    clear_issue()
    eligible = False
    def accepted(text):
        try:
            return validator is None or bool(validator(text))
        except (ValueError, TypeError, KeyError):
            return False
    for entry in providers():
        name, model = entry['provider'], entry['model']
        if not entry['configured'] or not entry['confirmed_free']:
            continue
        eligible = True
        key = cache_key(name, model, prompt)
        hit = cached(key)
        if hit and accepted(hit):
            clear_issue()
            return hit
        if hit:
            with closing(get_connection()) as db, db:
                db.execute('DELETE FROM ai_response_cache WHERE cache_key=?', (key,))
        if not reserve(name):
            record_issue(name, 'quota')
            continue
        answer = callers[name](prompt)
        if answer:
            if not accepted(answer):
                record_issue(name, 'format')
                continue
            save_cache(key, answer)
            clear_issue()
            return answer
    if not eligible:
        record_issue('setup', 'configuration')
    return None


def stream_failure(reason, partial=False):
    messages = {
        'length': 'The model reached its output limit. Choose a shorter answer format or ask a narrower question.',
        'content_filter': 'The provider stopped this response through its content filter. Try rephrasing your question.',
        'timeout': 'The AI provider timed out. Please try again.',
        'connection': 'The connection to the AI provider was interrupted. Please try again.',
        'quota': 'A local or provider rate or quota limit was reached. Check AI usage and try again after the reset.',
        'auth': 'The provider rejected the API key. Check its key in your local .env and restart the server.',
        'access': 'The provider denied access. Check model permissions, account restrictions, or budget limits.',
        'credits': 'The provider blocked this account through a credit or budget restriction. Use an eligible free account or another configured free provider.',
        'model': 'The selected model is unavailable. Choose an available free model in setup.',
        'format': 'The model returned an invalid quiz response. Try another free model or request fewer questions.',
        'configuration': 'No eligible AI provider is configured. Check the API key and free-tier confirmation in setup.',
        'provider_error': 'The AI provider returned an error. Please try again later.',
        'incomplete': 'The AI provider ended the stream before completing its answer. Please try again.',
    }
    message = messages.get(reason, messages['incomplete'])
    if partial:
        message += ' This partial answer was not saved.'
    return RuntimeError(message)


def stream(prompt):
    """Yield actual provider deltas; an aborted/partial answer is never cached."""
    last_failure = None
    for entry in providers():
        name, model = entry['provider'], entry['model']
        if not entry['configured'] or not entry['confirmed_free']:
            continue
        key = cache_key(name, model, prompt)
        hit = cached(key)
        if hit:
            yield hit
            return
        if not reserve(name):
            continue
        pieces, completed, failed, reason = [], False, False, 'incomplete'
        logger.info('Starting %s stream (model: %s)', name, model)
        try:
            with urllib.request.urlopen(request_for(name, model, prompt, True), timeout=60) as response:
                for line in response:
                    line = line.decode('utf-8').strip()
                    if not line.startswith('data:'):
                        continue
                    data = line[5:].strip()
                    if data == '[DONE]':
                        completed = not failed
                        break
                    event = json.loads(data)
                    if event.get('error'):
                        error = event['error']
                        code = str(error.get('code', '')) if isinstance(error, dict) else ''
                        reason = http_reason(int(code)) if code.isdigit() else 'provider_error'
                        if reason == 'quota':
                            pause_after_limit(name, getattr(response, 'headers', None))
                        failed = True
                        break
                    choices = event.get('choices', []) if name != 'gemini' else event.get('candidates', [])
                    finish = next((c.get('finish_reason') or c.get('finishReason') for c in choices
                                   if c.get('finish_reason') or c.get('finishReason')), None)
                    if finish in ('stop', 'STOP'):
                        completed = True
                    elif finish:
                        failed = True
                        reason = 'length' if finish in ('length', 'MAX_TOKENS') else 'content_filter' if finish in ('content_filter', 'SAFETY') else 'provider_error'
                    text = read_text(name, event, True)
                    if text:
                        pieces.append(text)
                        yield text
                    if failed:
                        break
                if pieces and completed and not failed:
                    save_cache(key, ''.join(pieces))
                    logger.info('%s stream completed', name)
                    return
        except urllib.error.HTTPError as exc:
            reason = http_reason(exc.code)
            logger.warning('%s stream HTTP failure (%s)', name, exc.code)
            if exc.code == 429:
                pause_after_limit(name, exc.headers)
        except TimeoutError:
            reason = 'timeout'
        except OSError:
            reason = 'connection'
        except ValueError:
            reason = 'provider_error'
        logger.warning('%s stream failed (%s; partial=%s)', name, reason, bool(pieces))
        last_failure = stream_failure(reason, bool(pieces))
        if pieces:
            raise last_failure
    if last_failure:
        raise last_failure
    raise RuntimeError('No free AI quota is available. Check free-tier confirmation and usage limits in AI usage.')
