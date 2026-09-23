import os
import logging
import time
from dotenv import load_dotenv

load_dotenv()
from typing import List, Optional

logger = logging.getLogger(__name__)


# Models are tried in order. Flash-Lite is intended for high-throughput use.
GEMINI_MODELS = [
    "gemini-3.5-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.8-flash",
]


def call_gemini(prompt: str, max_attempts_per_model: int = 2) -> Optional[str]:
    """
    Central Gemini caller with retry + model fallback.

    Returns:
        Generated text, or None if all configured models fail.
    """
    api_key = os.environ.get("GEMINI_API_KEY")

    if not api_key:
        logger.warning("GEMINI_API_KEY is not configured.")
        return None

    try:
        from google import genai
        client = genai.Client(api_key=api_key)
    except Exception as e:
        logger.exception("Could not initialize Gemini client: %s", e)
        return None

    for model in GEMINI_MODELS:
        for attempt in range(1, max_attempts_per_model + 1):
            try:
                logger.info(
                    "Calling Gemini model=%s attempt=%d/%d",
                    model,
                    attempt,
                    max_attempts_per_model,
                )

                response = client.models.generate_content(
                    model=model,
                    contents=prompt,
                )

                text = getattr(response, "text", None)

                if text and text.strip():
                    logger.info("Gemini request succeeded with model=%s", model)
                    return text.strip()

                logger.warning(
                    "Gemini returned an empty response from model=%s",
                    model,
                )

            except Exception as e:
                logger.warning(
                    "Gemini failed: model=%s attempt=%d error=%s",
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

    logger.error("All Gemini models failed.")
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

    answer = call_gemini(prompt)

    if answer is None:
        logger.warning("Gemini unavailable. Using local Q&A fallback.")
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

    answer = call_gemini(prompt)

    if answer is None:
        logger.warning(
            "Gemini unavailable for summarization."
        )
        answer = (
            "*(Gemini is temporarily unavailable.)*\n\n"
            "The document was successfully retrieved, but an "
            "AI-generated summary could not be produced right now."
        )

    return {
        "answer": answer,
        "citations": []
    }


def fallback_synthesize(prompt: str) -> str:
    """
    Local fallback when no Gemini model is available.
    """
    return (
        "*(Gemini is temporarily unavailable. "
        "Showing retrieval fallback.)*\n\n"
        "The system successfully retrieved relevant document "
        "content, but an AI-generated conversational answer "
        "could not be produced at this moment."
    )


def generate_notes(doc_title: str, chunks: List[dict]) -> dict:
    """
    Generates beautifully formatted, humanized study notes
    from the document chunks.
    """
    if not chunks:
        return {
            "notes": "No document content found to generate notes.",
            "citations": []
        }

    combined_text = "\n\n".join(
        [c.get("content", "") for c in chunks]
    )

    if len(combined_text) > 80000:
        combined_text = (
            combined_text[:80000]
            + "... (truncated for length)"
        )

    prompt = f"""
You are an expert educator and note-taker.

Create beautiful, highly readable and structured study notes
from the document titled "{doc_title}".

Guidelines:
- Use Markdown formatting.
- Use clear headings and subheadings.
- Use bold text for important terms.
- Use concise bullet points.
- Include definitions where the document provides them.
- Include important examples from the document.
- Highlight important points.
- Add a short key-takeaways section.
- Make the notes feel like carefully prepared human study notes.
- Do NOT add facts that are not supported by the document.
- Preserve the terminology used by the document.

Document Text:
{combined_text}

Generate the notes below:
"""

    notes = call_gemini(prompt)

    if notes is None:
        logger.warning(
            "Gemini unavailable for notes generation."
        )
        notes = (
            "# Notes temporarily unavailable\n\n"
            "The document was successfully processed, but "
            "Gemini is temporarily unavailable. Please try "
            "generating the notes again."
        )

    return {
        "notes": notes,
        "citations": []
    }