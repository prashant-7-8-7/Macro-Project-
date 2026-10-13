import os
import logging
import time
from dotenv import load_dotenv

load_dotenv()
from typing import List, Optional

logger = logging.getLogger(__name__)


import json
import urllib.request
import urllib.error

# Models are tried in order.
LLM_MODELS = [
    "meta-llama/llama-3.1-8b-instruct",
    "meta-llama/llama-3.3-70b-instruct",
    "mistralai/mistral-7b-instruct"
]


def _call_gemini_api(api_key: str, prompt: str) -> Optional[str]:
    """Call Google Gemini using google-genai SDK or direct REST with modern models."""
    gemini_models = ["gemini-3.8-flash", "gemini-3.5-flash", "gemini-flash-latest", "gemini-2.5-flash"]
    try:
        from google import genai
        client = genai.Client(api_key=api_key)
        for model in gemini_models:
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=prompt
                )
                if response.text and response.text.strip():
                    logger.info("Gemini SDK request succeeded with model=%s", model)
                    return response.text.strip()
            except Exception as e:
                logger.warning("Gemini SDK failed model=%s: %s", model, e)
    except Exception as e:
        logger.warning("Failed to initialize google-genai client: %s", e)

    # REST fallback
    for model in gemini_models:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
            payload = {
                "contents": [{"parts": [{"text": prompt}]}]
            }
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                text = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                if text and text.strip():
                    logger.info("Gemini REST request succeeded with model=%s", model)
                    return text.strip()
        except Exception as e:
            logger.warning("Gemini REST failed model=%s: %s", model, e)
    return None

def _call_groq_api(api_key: str, prompt: str) -> Optional[str]:
    """Groq Cloud API caller."""
    groq_models = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"]
    for model in groq_models:
        try:
            url = "https://api.groq.com/openai/v1/chat/completions"
            payload = {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.4
            }
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}"
                },
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                if text and text.strip():
                    logger.info("Groq request succeeded with model=%s", model)
                    return text.strip()
        except Exception as e:
            logger.warning("Groq failed model=%s: %s", model, e)
    return None

def call_llm(prompt: str, max_attempts_per_model: int = 2) -> Optional[str]:
    """
    Central LLM caller supporting Google Gemini, Groq, and OpenRouter.
    Automatically detects the key provider.
    """
    gemini_key = os.environ.get("GEMINI_API_KEY")
    groq_key = os.environ.get("GROQ_API_KEY")
    openrouter_key = os.environ.get("OPENROUTER_API_KEY")
    api_key = gemini_key or groq_key or openrouter_key

    if not api_key:
        logger.warning("API key is not configured.")
        return None

    # 1. Google Gemini key (supports AIza..., AQ..., or any configured GEMINI_API_KEY)
    if gemini_key:
        res = _call_gemini_api(gemini_key, prompt)
        if res:
            return res

    # 2. Groq key
    if groq_key or (api_key and api_key.startswith("gsk_")):
        res = _call_groq_api(groq_key or api_key, prompt)
        if res:
            return res

    # 3. OpenRouter / OpenAI compatible fallback
    url = "https://openrouter.ai/api/v1/chat/completions"

    for model in LLM_MODELS:
        for attempt in range(1, max_attempts_per_model + 1):
            try:
                logger.info(
                    "Calling OpenRouter model=%s attempt=%d/%d",
                    model,
                    attempt,
                    max_attempts_per_model,
                )

                data = {
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.4,
                    "max_tokens": 4096
                }
                req = urllib.request.Request(
                    url, 
                    data=json.dumps(data).encode("utf-8"),
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {api_key}"
                    },
                    method="POST"
                )

                with urllib.request.urlopen(req, timeout=60) as response:
                    res_body = response.read().decode("utf-8")
                    res_json = json.loads(res_body)
                    text = res_json.get("choices", [{}])[0].get("message", {}).get("content", "")

                if text and text.strip():
                    logger.info("LLM request succeeded with model=%s", model)
                    return text.strip()

            except Exception as e:
                logger.warning(
                    "LLM failed: model=%s attempt=%d error=%s",
                    model,
                    attempt,
                    e,
                )

                if attempt < max_attempts_per_model:
                    time.sleep(1.5)

        logger.warning(
            "Model %s unavailable after %d attempts. Trying next model.",
            model,
            max_attempts_per_model,
        )

    logger.error("All Groq models failed.")
    return None


def synthesize_answer(query: str, contexts: List[dict]) -> dict:
    """
    Given a query and a list of context chunks (with text, document name, page),
    generates an answer using an LLM.
    """
    if not contexts:
        return {
            "answer": "No relevant documents found to answer your question.",
            "citations": []
        }

    contexts = sorted(
        contexts,
        key=lambda x: (
            x.get("filename", ""),
            x.get("page_number", 0),
            x.get("chunk_index", 0),
        ),
    )

    context_text = ""
    citations = []

    for i, ctx in enumerate(contexts):
        doc_name = ctx.get("filename", "Unknown Document")
        page = ctx.get("page_number", 1)
        content = ctx.get("content", "")
        score = ctx.get("similarity", ctx.get("rank_score", 0))

        context_text += (
            f"\n--- Source [{i+1}]: {doc_name} "
            f"(Page {page}) ---\n{content}\n"
        )

        citations.append({
            "id": i + 1,
            "filename": doc_name,
            "page_number": page,
            "chunk_id": ctx.get("id", ""),
            "score": round(score, 4),
        })

    prompt = f"""
You are an intelligent AI assistant. Use the following document context
to answer the user's question.

Rules:
- Answer only from the provided document context.
- If the answer cannot be found in the context, state that clearly.
- Do not invent facts.
- Cite sources using the [Source N] format.

Context:
{context_text}

Question: {query}

Answer:
"""

    answer = call_llm(prompt)

    if answer is None:
        logger.warning("LLM unavailable. Using local Q&A fallback.")
        answer = fallback_synthesize(prompt)

    return {
        "answer": answer,
        "citations": citations
    }


def summarize_document(doc_title: str, chunks: List[dict]) -> dict:
    """
    Generates a full summary of a document based on its ordered chunks.
    """
    if not chunks:
        return {
            "answer": "No document content found to summarize.",
            "citations": []
        }

    combined_text = "\n\n".join(
        [c.get("content", "") for c in chunks]
    )

    if len(combined_text) > 100000:
        combined_text = (
            combined_text[:100000]
            + "... (truncated for length)"
        )

    prompt = f"""
Provide a comprehensive and well-structured summary of the following
document titled "{doc_title}".

Highlight:
- key themes
- main arguments
- important concepts
- important conclusions

Use only the supplied document text. Do not add outside information.

Document Text:
{combined_text}
"""

    answer = call_llm(prompt)

    if answer is None:
        logger.warning(
            "LLM unavailable for summarization."
        )
        answer = (
            "*(AI is temporarily unavailable.)*\n\n"
            "The document was successfully retrieved, but an "
            "AI-generated summary could not be produced right now."
        )

    return {
        "answer": answer,
        "citations": []
    }


def fallback_synthesize(prompt: str) -> str:
    """
    Local fallback when no LLM is available.
    """
    return (
        "*(AI is temporarily unavailable. "
        "Showing retrieval fallback.)*\n\n"
        "The system successfully retrieved relevant document "
        "content, but an AI-generated conversational answer "
        "could not be produced at this moment."
    )


def generate_notes(doc_title: str, chunks: List[dict]) -> dict:
    """
    Generates beautifully formatted, structured study notes
    from the document chunks (JSON format for notebook renderer).
    """
    if not chunks:
        return {
            "notes": None,
            "error": "No document content found to generate notes."
        }

    combined_text = "\n\n".join(
        [c.get("content", "") for c in chunks]
    )

    if len(combined_text) > 40000:
        combined_text = (
            combined_text[:40000]
            + "... (truncated for length)"
        )

    title_hint = f'Title suggestion: "{doc_title}"' if doc_title else ''

    prompt = f"""You are an expert student note-maker. Generate structured study notes in JSON from the document below.
{title_hint}

RULES:
1. Use ONLY information from the document.
2. Return ONLY valid JSON — no markdown fences.
3. Generate 4-7 sections.
4. For "color": use one of: green, blue, red, orange, purple, teal (alternate them).
5. For "layout": "full" (text+bullets), "split" (text+bullets LEFT, keyBox RIGHT).

JSON structure:
{{
  "title": "{doc_title or 'Study Notes'}",
  "subject": "Document Summary",
  "quote": "Key quote under 100 chars",
  "sections": [
    {{
      "number": 1,
      "heading": "Section Heading",
      "color": "green",
      "layout": "split",
      "content": "1-3 sentence explanation. Use **bold** for key terms.",
      "bullets": ["Point one", "Point two"],
      "keyBox": {{ "title": "⭐ Key Idea", "items": ["item 1", "item 2"] }},
      "tip": "Remember: important tip"
    }}
  ],
  "keyTakeaways": ["Takeaway 1", "Takeaway 2", "Takeaway 3"],
  "remember": ["Fact 1", "Fact 2"]
}}

DOCUMENT:
{combined_text}

Return ONLY the raw JSON object."""

    raw_response = call_llm(prompt)

    if raw_response is None:
        logger.warning("LLM unavailable for notes generation.")
        return {
            "notes": None,
            "error": "AI is temporarily unavailable. Please verify GEMINI_API_KEY."
        }

    # Clean code fences
    s = str(raw_response).strip()
    s = s.replace("```json", "").replace("```JSON", "").replace("```", "").strip()
    start = s.find('{')
    end = s.rfind('}')
    if start != -1 and end != -1 and end > start:
        s = s[start:end+1]

    try:
        data = json.loads(s)
        return {"notes": data}
    except Exception as e:
        logger.warning("Failed to parse JSON notes from LLM: %s", e)
        # Fallback dictionary structure
        return {
            "notes": {
                "title": doc_title or "Study Notes",
                "subject": "Summary",
                "quote": "Key concepts extracted from document",
                "sections": [
                    {
                        "number": 1,
                        "heading": "Overview",
                        "color": "blue",
                        "layout": "full",
                        "content": s[:600],
                        "bullets": ["Review complete document for details"],
                        "keyBox": {"title": "Note", "items": ["Generated from document content"]},
                        "tip": "Read original source for more context"
                    }
                ],
                "keyTakeaways": ["Document parsed successfully"],
                "remember": ["Review full document text"]
            }
        }