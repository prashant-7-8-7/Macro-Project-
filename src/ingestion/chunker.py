import re
from typing import List, Dict, Any
from src.config import CHUNK_SIZE, CHUNK_OVERLAP

# Common Latin and Western abbreviations to protect from false sentence splits
COMMON_ABBREVIATIONS = {
    'dr', 'mr', 'mrs', 'ms', 'prof', 'sr', 'jr', 'vs', 'etc', 'eg', 'ie',
    'al', 'inc', 'ltd', 'corp', 'co', 'jan', 'feb', 'mar', 'apr', 'jun',
    'jul', 'aug', 'sep', 'sept', 'oct', 'nov', 'dec', 'dept', 'univ', 'approx'
}


class TextChunker:
    """
    Unicode-aware text chunker supporting multilingual sentence splitting,
    character/token budgets for unsegmented scripts, and page number metadata preservation.
    """

    @staticmethod
    def split_sentences(text: str) -> List[str]:
        """
        Splits text into sentences using a Unicode-aware method supporting:
        . ! ? । ॥ 。 ！？ ؟ ۔ ‥ … and newlines.
        Safely avoids splitting on decimal numbers (e.g. 3.14) and abbreviations (e.g. Dr., U.S.).
        """
        if not text:
            return []

        # 1. Protect decimal numbers (digits on both sides: 3.14 -> 3<DEC_DOT>14)
        s = re.sub(r'(?<=\d)\.(?=\d)', '<DEC_DOT>', text)

        # 2. Protect multi-dot acronyms like U.S. or e.g. or i.e.
        s = re.sub(r'\b([A-Za-z])\.([A-Za-z])\.', r'\1<ACR_DOT>\2<ACR_DOT>', s)

        # 3. Protect common abbreviations and single-letter initials followed by dot
        def mask_abbr(match: re.Match) -> str:
            word = match.group(1)
            if word.lower() in COMMON_ABBREVIATIONS or len(word) == 1:
                return f"{word}<ABBR_DOT>"
            return match.group(0)

        s = re.sub(r'\b([A-Za-z]{1,6})\.(?=\s+[A-Za-z0-9]|\s*$)', mask_abbr, s)

        # 4. Unicode sentence terminators:
        # Western: . ! ?
        # Indic/Devanagari: । (\u0964) ॥ (\u0965)
        # CJK: 。 (\u3002) ！ (\uff01) ？ (\uff1f)
        # Arabic/Urdu: ؟ (\u061f) ۔ (\u06d4)
        # Ellipsis: ‥ (\u2025) … (\u2026)
        # Newlines: \n
        pattern = r'([^.!?!॥\u0964\u0965\u3002\uff01\uff1f\u061f\u06d4\u2025\u2026\n]+(?:[.!?॥\u0964\u0965\u3002\uff01\uff1f\u061f\u06d4\u2025\u2026]+|\n+|$))'
        parts = re.findall(pattern, s)

        sentences = []
        for p in parts:
            cleaned = (
                p.replace('<DEC_DOT>', '.')
                .replace('<ACR_DOT>', '.')
                .replace('<ABBR_DOT>', '.')
                .strip()
            )
            if cleaned:
                sentences.append(cleaned)

        # Fallback if regex returned nothing but text is present
        if not sentences and text.strip():
            sentences = [text.strip()]

        return sentences

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """
        Estimates token count using character count for unsegmented scripts (Chinese,
        Japanese, Thai) and whitespace-word count for spaced writing systems.
        """
        if not text:
            return 0

        cjk_and_unsegmented = 0
        spaced_chars = []

        for char in text:
            code = ord(char)
            # CJK Unified, Hiragana, Katakana, Hangul, Thai
            if (
                0x4E00 <= code <= 0x9FFF
                or 0x3040 <= code <= 0x309F
                or 0x30A0 <= code <= 0x30FF
                or 0xAC00 <= code <= 0xD7AF
                or 0x0E00 <= code <= 0x0E7F
            ):
                cjk_and_unsegmented += 1
            else:
                spaced_chars.append(char)

        words = "".join(spaced_chars).split()
        return cjk_and_unsegmented + len(words)

    @staticmethod
    def _is_unsegmented(text: str) -> bool:
        if not text:
            return False
        cjk_count = sum(
            1 for c in text
            if (
                0x4E00 <= ord(c) <= 0x9FFF
                or 0x3040 <= ord(c) <= 0x30FF
                or 0xAC00 <= ord(c) <= 0xD7AF
                or 0x0E00 <= ord(c) <= 0x0E7F
            )
        )
        return cjk_count > (len(text) * 0.25)

    @staticmethod
    def _split_oversized_sentence(sent: str, chunk_size: int, overlap: int) -> List[Dict[str, Any]]:
        """Splits an oversized single sentence by character or word slices with overlap."""
        results = []
        step = max(1, chunk_size - overlap)
        if TextChunker._is_unsegmented(sent):
            for i in range(0, len(sent), step):
                piece = sent[i:i + chunk_size].strip()
                if piece:
                    results.append({
                        "content": piece,
                        "token_count": TextChunker.estimate_tokens(piece)
                    })
        else:
            words = sent.split()
            for i in range(0, len(words), step):
                piece = " ".join(words[i:i + chunk_size]).strip()
                if piece:
                    results.append({
                        "content": piece,
                        "token_count": TextChunker.estimate_tokens(piece)
                    })
        return results

    @staticmethod
    def chunk_pages(
        pages: List[Dict[str, Any]],
        chunk_size: int = CHUNK_SIZE,
        overlap: int = CHUNK_OVERLAP,
    ) -> List[Dict[str, Any]]:
        """
        Splits pages into semantic chunks respecting Unicode sentence boundaries.
        Preserves page number metadata and maintains small chunk overlap.
        """
        chunks = []
        global_chunk_idx = 0

        for page in pages:
            text = page.get('text', '')
            page_num = page.get('page_number', 1)

            sentences = TextChunker.split_sentences(text)
            if not sentences:
                continue

            current_chunk_sentences = []
            current_length = 0

            for sent in sentences:
                sent_tokens = TextChunker.estimate_tokens(sent)

                # Handle exceptionally large individual sentence
                if sent_tokens > chunk_size:
                    # Flush any previously accumulated sentences
                    if current_chunk_sentences:
                        chunk_content = " ".join(current_chunk_sentences).strip()
                        chunks.append({
                            "chunk_index": global_chunk_idx,
                            "content": chunk_content,
                            "token_count": current_length,
                            "page_number": page_num
                        })
                        global_chunk_idx += 1
                        current_chunk_sentences = []
                        current_length = 0

                    sub_parts = TextChunker._split_oversized_sentence(sent, chunk_size, overlap)
                    for sp in sub_parts:
                        chunks.append({
                            "chunk_index": global_chunk_idx,
                            "content": sp["content"],
                            "token_count": sp["token_count"],
                            "page_number": page_num
                        })
                        global_chunk_idx += 1
                    continue

                if current_length + sent_tokens > chunk_size and current_chunk_sentences:
                    chunk_content = " ".join(current_chunk_sentences).strip()
                    chunks.append({
                        "chunk_index": global_chunk_idx,
                        "content": chunk_content,
                        "token_count": current_length,
                        "page_number": page_num
                    })
                    global_chunk_idx += 1

                    # Compute overlap from trailing sentences
                    overlap_sentences = []
                    overlap_tokens = 0
                    for s in reversed(current_chunk_sentences):
                        st = TextChunker.estimate_tokens(s)
                        if overlap_tokens + st <= overlap:
                            overlap_sentences.insert(0, s)
                            overlap_tokens += st
                        else:
                            # Keep at least one sentence for overlap if multiple existed
                            if not overlap_sentences and len(current_chunk_sentences) > 1:
                                overlap_sentences.insert(0, s)
                                overlap_tokens += st
                            break

                    current_chunk_sentences = list(overlap_sentences) + [sent]
                    current_length = overlap_tokens + sent_tokens
                else:
                    current_chunk_sentences.append(sent)
                    current_length += sent_tokens

            # Flush remaining sentences for this page
            if current_chunk_sentences:
                chunk_content = " ".join(current_chunk_sentences).strip()
                if not chunks or chunks[-1]["content"] != chunk_content:
                    chunks.append({
                        "chunk_index": global_chunk_idx,
                        "content": chunk_content,
                        "token_count": current_length,
                        "page_number": page_num
                    })
                    global_chunk_idx += 1

        return chunks
