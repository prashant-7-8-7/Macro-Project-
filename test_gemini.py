import os
from dotenv import load_dotenv
import logging

logging.basicConfig(level=logging.INFO)

load_dotenv()

api_key = os.environ.get("GEMINI_API_KEY")
print(f"API Key loaded: {'Yes' if api_key else 'No'}")

try:
    from google import genai
    print("genai imported successfully")
    client = genai.Client(api_key=api_key)
    print("Client initialized")
    print("Available models:")
    for m in client.models.list():
        print(m.name)
except Exception as e:
    print(f"Exception: {e}")
