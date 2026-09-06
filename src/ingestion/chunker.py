from typing import List, Dict, Any
import re
from src.config import CHUNK_SIZE, CHUNK_OVERLAP

class TextChunker:
    @staticmethod
    def chunk_pages(pages: List[Dict[str, Any]], chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> List[Dict[str, Any]]:
        """
        Splits pages into smaller chunks with overlap.
        Preserves page number metadata.
        """
        chunks = []
        global_chunk_idx = 0
        
        for page in pages:
            text = page['text']
            page_num = page['page_number']
            
            # Simple whitespace-based tokenization approximation
            words = re.split(r'(\s+)', text)
            
            current_chunk = []
            current_length = 0
            
            i = 0
            while i < len(words):
                word = words[i]
                word_len = len(word.strip())
                
                # Treat spaces as 0 length for token count estimation
                if word_len > 0:
                    current_length += 1
                    
                current_chunk.append(word)
                
                if current_length >= chunk_size:
                    chunks.append({
                        "chunk_index": global_chunk_idx,
                        "content": "".join(current_chunk).strip(),
                        "token_count": current_length,
                        "page_number": page_num
                    })
                    global_chunk_idx += 1
                    
                    # Backtrack for overlap
                    overlap_count = 0
                    back_idx = len(current_chunk) - 1
                    while back_idx >= 0 and overlap_count < overlap:
                        if len(current_chunk[back_idx].strip()) > 0:
                            overlap_count += 1
                        back_idx -= 1
                        
                    current_chunk = current_chunk[back_idx+1:]
                    current_length = overlap
                    
                i += 1
                
            if current_length > 0 and "".join(current_chunk).strip():
                chunks.append({
                    "chunk_index": global_chunk_idx,
                    "content": "".join(current_chunk).strip(),
                    "token_count": current_length,
                    "page_number": page_num
                })
                global_chunk_idx += 1
                
        return chunks
