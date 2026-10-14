import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


def detect_by_script(text: str) -> Optional[str]:
    """Lightweight Unicode script heuristic for non-Latin writing systems."""
    counts = {}
    for c in text:
        code = ord(c)
        if 0x0900 <= code <= 0x097F:
            counts['hi'] = counts.get('hi', 0) + 1
        elif 0x0600 <= code <= 0x06FF or 0x0750 <= code <= 0x077F or 0x08A0 <= code <= 0x08FF:
            counts['ar'] = counts.get('ar', 0) + 1
        elif 0x0B80 <= code <= 0x0BFF:
            counts['ta'] = counts.get('ta', 0) + 1
        elif 0x0980 <= code <= 0x09FF:
            counts['bn'] = counts.get('bn', 0) + 1
        elif 0x0400 <= code <= 0x04FF:
            counts['ru'] = counts.get('ru', 0) + 1
        elif 0x3040 <= code <= 0x309F or 0x30A0 <= code <= 0x30FF:
            counts['ja'] = counts.get('ja', 0) + 1
        elif 0xAC00 <= code <= 0xD7AF or 0x1100 <= code <= 0x11FF:
            counts['ko'] = counts.get('ko', 0) + 1
        elif 0x4E00 <= code <= 0x9FFF:
            counts['zh'] = counts.get('zh', 0) + 1

    if counts:
        # Japanese texts commonly mix Kanji (CJK) with Hiragana/Katakana
        if counts.get('ja', 0) > 0:
            return 'ja'
        top_script, count = max(counts.items(), key=lambda x: x[1])
        if count >= 3:
            return top_script
    return None


def detect_text_language(text: str) -> str:
    """
    Detects the primary language code (e.g. 'en', 'es', 'hi', 'ar', 'zh', 'ja', 'ru', 'fr', 'ta', 'bn')
    using Unicode script heuristics and langdetect.
    """
    if not text or not text.strip():
        return 'en'

    sample = text.strip()[:3000]

    # 1. Check distinct punctuation or non-Latin scripts
    if '¿' in sample or '¡' in sample:
        return 'es'

    script_lang = detect_by_script(sample)

    # 2. Try langdetect for high accuracy
    try:
        from langdetect import detect, DetectorFactory
        DetectorFactory.seed = 0
        lang = detect(sample)
        if lang:
            # Standardize codes
            if lang.startswith('zh'):
                return 'zh'
            # Japanese text with kanji might sometimes register as zh; prioritize ja if kana is present
            if script_lang == 'ja' and lang.startswith('zh'):
                return 'ja'
            return lang.lower()
    except Exception as e:
        logger.debug(f"langdetect lookup failed: {e}")

    # 3. Fallback to script heuristic
    if script_lang:
        return script_lang

    return 'en'


def detect_document_language(pages: List[Dict[str, Any]]) -> str:
    """Detects document language from list of parsed page dicts."""
    if not pages:
        return 'en'
    combined = " ".join(p.get('text', '') for p in pages[:5])
    return detect_text_language(combined)
