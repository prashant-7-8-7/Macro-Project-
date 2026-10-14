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


from src.ingestion.detector import detect_text_language

LANGUAGE_NAMES = {
    "en": "English",
    "hi": "Hindi (हिंदी)",
    "es": "Spanish (Español)",
    "fr": "French (Français)",
    "ar": "Arabic (العربية)",
    "zh": "Chinese (中文)",
    "ja": "Japanese (日本語)",
    "ru": "Russian (Русский)",
    "de": "German (Deutsch)",
    "ta": "Tamil (தமிழ்)",
    "bn": "Bengali (বাংলা)",
    "pt": "Portuguese (Português)",
    "it": "Italian (Italiano)",
    "ko": "Korean (한국어)",
    "tr": "Turkish (Türkçe)",
    "ur": "Urdu (اردو)",
}

NO_CONTEXT_MESSAGES = {
    "en": "No relevant documents found to answer your question.",
    "hi": "आपके प्रश्न का उत्तर देने के लिए कोई प्रासंगिक दस्तावेज़ नहीं मिला।",
    "es": "No se encontraron documentos relevantes para responder a su pregunta.",
    "pt": "Nenhum documento relevante foi encontrado para responder à sua pergunta.",
    "ar": "لم يتم العثور على مستندات ذات صلة للإجابة على سؤالك.",
    "zh": "未找到相关文档来回答您的问题。",
    "ja": "ご質問に答えるための関連ドキュメントが見つかりませんでした。",
    "fr": "Aucun document pertinent n'a été trouvé pour répondre à votre question.",
    "ru": "Не найдено релевантных документов для ответа на ваш вопрос.",
    "de": "Keine relevanten Dokumente gefunden, um Ihre Frage zu beantworten.",
    "ta": "உங்கள் கேள்விக்கு பதிலளிக்க தொடர்புடைய ஆவணங்கள் எதுவும் கிடைக்கவில்லை.",
    "bn": "আপনার প্রশ্নের উত্তর দেওয়ার জন্য কোনো প্রাসঙ্গিক নথি পাওয়া যায়নি।",
    "it": "Nessun documento rilevante trovato per rispondere alla tua domanda.",
    "ko": "질문에 답변할 수 있는 관련 문서를 찾을 수 없습니다.",
}

AI_UNAVAILABLE_MESSAGES = {
    "en": "*(AI is temporarily unavailable.)*\n\nThe document was successfully retrieved, but an AI-generated response could not be produced right now.",
    "hi": "*(एआई अस्थायी रूप से अनुपलब्ध है।)*\n\nदस्तावेज़ सफलतापूर्वक प्राप्त कर लिया गया था, लेकिन अभी एआई द्वारा प्रतिक्रिया उत्पन्न नहीं की जा सकी।",
    "es": "*(La IA no está disponible temporalmente.)*\n\nEl documento se recuperó con éxito, pero en este momento no se pudo producir una respuesta generada por IA.",
    "ar": "*(الذكاء الاصطناعي غير متوفر مؤقتًا.)*\n\nتم استرداد المستند بنجاح، ولكن تعذر إنشاء استجابة بواسطة الذكاء الاصطناعي الآن.",
    "zh": "*(AI服务暂时不可用。)*\n\n文档已成功检索，但目前无法生成AI回答。",
    "ja": "*(AIは一時的に利用できません。)*\n\nドキュメントは正常に取得されましたが、現時点ではAIによる回答を生成できませんでした。"
}


def synthesize_answer(query: str, contexts: List[dict]) -> dict:
    """
    Given a query and a list of context chunks (with text, document name, page),
    generates an answer using an LLM in the language of the query.
    """
    q_lang = detect_text_language(query)
    q_lang_name = LANGUAGE_NAMES.get(q_lang, q_lang)

    if not contexts:
        return {
            "answer": NO_CONTEXT_MESSAGES.get(q_lang, NO_CONTEXT_MESSAGES["en"]),
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

Language Requirement:
- Respond in the language of the user's question ({q_lang_name}), unless the user explicitly requests another language.

Rules:
- Answer only from the provided document context.
- If the answer cannot be found in the context, state that clearly in {q_lang_name} instead of guessing.
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
        answer = fallback_synthesize(prompt, q_lang=q_lang)

    return {
        "answer": answer,
        "citations": citations
    }


def summarize_document(doc_title: str, chunks: List[dict], doc_lang: Optional[str] = None) -> dict:
    """
    Generates a full summary of a document based on its ordered chunks in the document's language.
    """
    if not chunks:
        return {
            "answer": "No document content found to summarize.",
            "citations": []
        }

    combined_text = "\n\n".join(
        [c.get("content", "") for c in chunks]
    )

    if not doc_lang:
        doc_lang = (chunks[0].get("language") if chunks else None) or detect_text_language(combined_text[:3000])
    doc_lang_name = LANGUAGE_NAMES.get(doc_lang, doc_lang)

    if len(combined_text) > 100000:
        combined_text = (
            combined_text[:100000]
            + "... (truncated for length)"
        )

    prompt = f"""
Provide a comprehensive and well-structured summary of the following
document titled "{doc_title}".

Language Requirement:
- Write the summary in the document's language ({doc_lang_name}), unless the user asked for a different language.

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
        logger.warning("LLM unavailable for summarization.")
        answer = AI_UNAVAILABLE_MESSAGES.get(doc_lang, AI_UNAVAILABLE_MESSAGES["en"])

    return {
        "answer": answer,
        "citations": []
    }


def fallback_synthesize(prompt: str, q_lang: str = "en") -> str:
    """
    Local fallback when no LLM is available.
    """
    fallback_msgs = {
        "en": (
            "*(AI is temporarily unavailable. Showing retrieval fallback.)*\n\n"
            "The system successfully retrieved relevant document "
            "content, but an AI-generated conversational answer "
            "could not be produced at this moment."
        ),
        "hi": (
            "*(एआई अस्थायी रूप से अनुपलब्ध है। पुनःप्राप्ति फ़ॉलबैक दिखाया जा रहा है।)*\n\n"
            "सिस्टम ने प्रासंगिक दस्तावेज़ सामग्री प्राप्त कर ली है, लेकिन इस समय "
            "एआई-जनरेटेड संवादात्मक उत्तर तैयार नहीं किया जा सका।"
        ),
        "es": (
            "*(La IA no está disponible temporalmente. Mostrando alternativa de recuperación.)*\n\n"
            "El sistema recuperó correctamente el contenido relevante del documento, pero en este "
            "momento no se pudo producir una respuesta conversacional generada por IA."
        ),
        "ar": (
            "*(الذكاء الاصطناعي غير متوفر مؤقتًا. عرض المحتوى المسترجع بدلاً من ذلك.)*\n\n"
            "استرجع النظام بنجاح محتوى المستند ذي الصلة، ولكن يتعذر إنتاج إجابة "
            "محادثة تم إنشاؤها بواسطة الذكاء الاصطناعي في هذا الوقت."
        ),
        "zh": (
            "*(AI服务暂时不可用。显示检索回退内容。)*\n\n"
            "系统已成功检索到相关的文档内容，但目前无法生成AI对话回答。"
        ),
        "ja": (
            "*(AIは一時的に利用できません。取得フォールバックを表示しています。)*\n\n"
            "関連するドキュメントコンテンツは正常に取得されましたが、現時点ではAIによる回答を生成できませんでした。"
        )
    }
    return fallback_msgs.get(q_lang, fallback_msgs["en"])


def generate_notes(
    doc_title: str,
    chunks: List[dict],
    doc_lang: Optional[str] = None,
    detail_level: str = "standard",
    notes_language: Optional[str] = None,
) -> dict:
    """
    Generates beautifully formatted, structured, scalable study notes
    from document chunks using map-reduce (section-by-section extraction and merge).
    Supports 'original', 'en', and 'both' (dual-view).
    """
    from src.ai.notes import generate_hierarchical_notes
    return generate_hierarchical_notes(
        chunks=chunks,
        doc_title=doc_title,
        detail_level=detail_level,
        doc_lang=doc_lang,
        notes_language=notes_language,
    )


def retry_notes(
    doc_title: str,
    chunks: List[dict],
    target_section_indices: List[int],
    existing_notes: dict,
    detail_level: str = "standard",
    doc_lang: Optional[str] = None,
    notes_language: Optional[str] = None,
) -> dict:
    """
    Retries failed sections and splices them back into existing notes.
    """
    from src.ai.notes import retry_failed_sections
    return retry_failed_sections(
        chunks=chunks,
        doc_title=doc_title,
        target_section_indices=target_section_indices,
        existing_notes=existing_notes,
        detail_level=detail_level,
        doc_lang=doc_lang,
        notes_language=notes_language,
    )