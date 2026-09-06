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
    
    # Try multiple strings
    result = client.models.embed_content(
        model='gemini-embedding-2-preview',
        contents=['first chunk', 'second chunk'],
        config=types.EmbedContentConfig(output_dimensionality=384)
    )
    print(f"Number of embeddings (list of str): {len(result.embeddings)}")
    
    # What if we pass a list of strings as contents directly?
    print(dir(client.models))
except Exception as e:
    import traceback
    traceback.print_exc()
