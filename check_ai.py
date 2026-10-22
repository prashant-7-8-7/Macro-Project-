"""Check provider authentication with a metadata GET, without generating text."""
import argparse
import json
import os
from pathlib import Path
import urllib.error
import urllib.request

from dotenv import load_dotenv


ENDPOINTS = {
    'openrouter': 'https://openrouter.ai/api/v1/key',
    'groq': 'https://api.groq.com/openai/v1/models',
    'gemini': 'https://generativelanguage.googleapis.com/v1beta/models',
}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--provider', choices=ENDPOINTS, default='openrouter')
    args = parser.parse_args(argv)
    load_dotenv(Path(__file__).resolve().parent / '.env')
    key = os.environ.get(args.provider.upper() + '_API_KEY', '').strip()
    if not key:
        print(f'No {args.provider.upper()}_API_KEY is configured in your environment or .env.')
        return 2
    headers = {'x-goog-api-key': key} if args.provider == 'gemini' else {'Authorization': 'Bearer ' + key}
    request = urllib.request.Request(ENDPOINTS[args.provider], headers=headers, method='GET')
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            data = json.load(response)
        if not isinstance(data, dict) or data.get('error'):
            print('The provider returned an error instead of authentication metadata.')
            return 1
        expected = data.get('models') if args.provider == 'gemini' else data.get('data')
        if not isinstance(expected, dict if args.provider == 'openrouter' else list):
            print('The provider returned unexpected metadata; authentication could not be verified.')
            return 1
        print(f'{args.provider}: API key accepted by the metadata endpoint.')
        if args.provider == 'openrouter':
            metadata = data.get('data') or {}
            usage = metadata.get('free_model_daily_requests') or {}
            for field in ('used', 'limit', 'remaining'):
                value = usage.get(field)
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    print(f'Free-model daily requests {field}: {value}')
        print('No inference request or document text was sent. Model access and generation quota are separate checks.')
        return 0
    except urllib.error.HTTPError as exc:
        explanations = {
            401: 'Key rejected. Create a replacement key in the provider dashboard, update .env, and restart the app.',
            402: 'Account credit or budget restriction. Keep free models selected, or use another free provider.',
            403: 'Access denied. Check account restrictions, permissions, or provider budget settings.',
            429: 'Metadata request rate-limited. Wait for the provider limit to reset.',
        }
        print(f'{args.provider}: HTTP {exc.code}. ' + explanations.get(exc.code, 'Provider metadata check failed.'))
        return 1
    except (OSError, ValueError):
        print('Could not complete the metadata check. Check network access and try again.')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
