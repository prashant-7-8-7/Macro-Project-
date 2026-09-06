import os
import logging
from typing import List

logger = logging.getLogger(__name__)

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
        
    # Sort contexts chronologically (by filename, page number, then chunk index)
    contexts = sorted(contexts, key=lambda x: (x.get('filename', ''), x.get('page_number', 0), x.get('chunk_index', 0)))
        
    # Build context string
    context_text = ""
    citations = []
    
    for i, ctx in enumerate(contexts):
        doc_name = ctx.get('filename', 'Unknown Document')
        page = ctx.get('page_number', 1)
        content = ctx.get('content', '')
        score = ctx.get('similarity', ctx.get('rank_score', 0))
        
        context_text += f"\n--- Source [{i+1}]: {doc_name} (Page {page}) ---\n{content}\n"
        
        citations.append({
            "id": i+1,
            "filename": doc_name,
            "page_number": page,
            "chunk_id": ctx.get('id', ''),
            "score": round(score, 4)
        })

    prompt = f"""
    You are an intelligent AI assistant. Use the following document context to answer the user's question.
    If the answer cannot be found in the context, state that clearly instead of guessing.
    Cite your sources using the [Source N] format in your answer.
    
    Context:
    {context_text}
    
    Question: {query}
    
    Answer:
    """

    api_key = os.environ.get("GEMINI_API_KEY")
    if api_key:
        try:
            from google import genai
            client = genai.Client(api_key=api_key)
            response = client.models.generate_content(
                model='gemini-3.5-flash',
                contents=prompt
            )
            answer = response.text
        except Exception as e:
            logger.error(f"Error calling Gemini API: {e}")
            answer = fallback_synthesize(prompt)
    else:
        logger.info("No GEMINI_API_KEY found, using fallback local extraction.")
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
        return {"answer": "No document content found to summarize.", "citations": []}
        
    # Build a combined text (truncate if too long to prevent token limits on free tiers)
    combined_text = "\\n\\n".join([c.get('content', '') for c in chunks])
    if len(combined_text) > 100000:
        combined_text = combined_text[:100000] + "... (truncated for length)"
        
    prompt = f"Please provide a comprehensive and well-structured summary of the following document titled '{doc_title}'. Highlight the key themes, main arguments, and important conclusions.\\n\\nDocument Text:\\n{combined_text}"

    api_key = os.environ.get("GEMINI_API_KEY")
    if api_key:
        try:
            from google import genai
            client = genai.Client(api_key=api_key)
            response = client.models.generate_content(
                model='gemini-3.5-flash',
                contents=prompt
            )
            answer = response.text
        except Exception as e:
            logger.error(f"Error calling Gemini API for summarization: {e}")
            answer = fallback_synthesize(prompt)
    else:
        logger.info("No GEMINI_API_KEY found for summarization.")
        answer = "*(Note: LLM API key not configured. Cannot generate abstractive summary.)*\\n\\nPlease configure GEMINI_API_KEY to enable document summarization."
        
    return {
        "answer": answer,
        "citations": []
    }

def fallback_synthesize(prompt: str) -> str:
    """A simplistic extractive fallback when no LLM API is available."""
    return (
        "*(Note: LLM API key not configured. Showing raw context synthesis.)*\\n\\n"
        "Based on the retrieved documents, please review the highlighted sources below. "
        "The system retrieved relevant text but requires an LLM provider (e.g. Gemini) to generate a conversational answer."
    )

