import os
from dotenv import load_dotenv
from google import genai

load_dotenv()
client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

models = [
    "gemini-3.6-flash",
    "gemini-3.7-flash",
    "gemini-3.8-flash",
    "gemini-flash-latest",
    "gemini-pro-latest"
]

for m in models:
    try:
        r = client.models.generate_content(model=m, contents="Say yes")
        print(f"SUCCESS: {m} -> {r.text.strip()}")
    except Exception as e:
        print(f"FAILED: {m} -> {e}")
