"""Free-tier safeguards, local request budgets, caching, and streaming HTTP adapters."""
import hashlib
import json
import logging
import os
import time
import urllib.error
import urllib.request
from contextlib import closing
from datetime import datetime, timezone
from src.database.db import get_connection

logger = logging.getLogger(__name__)


def providers():
    result = []
    for name, default in [('gemini', 'gemini-3.8-flash'), ('groq', 'llama-3.1-8b-instant'), ('openrouter', 'openrouter/free')]:
        key = os.environ.get(name.upper() + '_API_KEY', '')
        model = default if name == 'openrouter' else os.environ.get(name.upper() + '_MODEL', default)
        # OpenRouter's free router only falls back to other free models.
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
    credential = os.environ.get(provider.upper() + '_API_KEY', '')
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
    key = os.environ.get(provider.upper() + '_API_KEY', '')
    headers = {'Content-Type': 'application/json'}
    if provider == 'gemini':
        action = 'streamGenerateContent?alt=sse' if stream else 'generateContent'
        url = f'https://generativelanguage.googleapis.com/v1beta/models/{model}:{action}'
        headers['x-goog-api-key'] = key
        payload = {'contents': [{'parts': [{'text': prompt}]}], 'generationConfig': {'maxOutputTokens': 4096}}
    else:
        url = 'https://api.groq.com/openai/v1/chat/completions' if provider == 'groq' else 'https://openrouter.ai/api/v1/chat/completions'
        headers['Authorization'] = 'Bearer ' + key
        payload = {'model': model, 'messages': [{'role': 'user', 'content': prompt}],
                   'temperature': 0.3, 'max_tokens': 4096, 'stream': stream}
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
            return read_text(provider, json.load(response)).strip() or None
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            block(provider)
        logger.warning('%s request failed with HTTP %s', provider, exc.code)
    except Exception as exc:
        logger.warning('%s request unavailable (%s)', provider, type(exc).__name__)
    return None


def generate(prompt, callers):
    for entry in providers():
        name, model = entry['provider'], entry['model']
        if not entry['configured'] or not entry['confirmed_free']:
            continue
        key = cache_key(name, model, prompt)
        hit = cached(key)
        if hit:
            return hit
        if not reserve(name):
            continue
        answer = callers[name](prompt)
        if answer:
            save_cache(key, answer)
            return answer
    return None


def stream(prompt):
    """Yield actual provider deltas; an aborted/partial answer is never cached."""
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
        pieces, completed, truncated = [], False, False
        try:
            with urllib.request.urlopen(request_for(name, model, prompt, True), timeout=60) as response:
                for line in response:
                    line = line.decode('utf-8').strip()
                    if not line.startswith('data:'):
                        continue
                    data = line[5:].strip()
                    if data == '[DONE]':
                        completed = not truncated
                        break
                    event = json.loads(data)
                    if any(c.get('finish_reason') not in (None, 'stop') for c in event.get('choices', [])):
                        truncated = True
                    text = read_text(name, event, True)
                    if text:
                        pieces.append(text)
                        yield text
                    if (name == 'gemini' and any(c.get('finishReason') == 'STOP' for c in event.get('candidates', []))) or any(c.get('finish_reason') == 'stop' for c in event.get('choices', [])):
                        completed = True
                if pieces and completed and not truncated:
                    save_cache(key, ''.join(pieces))
                    return
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                block(name)
        except (OSError, ValueError):
            pass
        if pieces:
            raise RuntimeError('Generation stopped before completion. Your partial answer was not saved.')
    raise RuntimeError('No free AI quota is available. Check free-tier confirmation and usage limits in AI usage.')
