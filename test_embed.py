import os
from dotenv import load_dotenv
import logging

logging.basicConfig(level=logging.INFO)
load_dotenv()
api_key = os.environ.get("GEMINI_API_KEY")

try:
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=api_key)
    
    # Try embedding with reduced dimensionality
    result = client.models.embed_content(
        model='gemini-embedding-2-preview',
        contents='hello world',
        config=types.EmbedContentConfig(output_dimensionality=384)
    )
    print(f"Embedding length: {len(result.embeddings[0].values)}")
    print(result.embeddings[0].values[:5])
except Exception as e:
    print(f"Exception: {e}")
