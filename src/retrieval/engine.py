import time
import logging
import numpy as np
from typing import List, Dict, Any

from src.database.repository import DocumentRepository
from src.ai.embeddings import EmbeddingEngine
from src.ai.vector_math import deserialize_embedding, compute_cosine_similarity
from src.retrieval.fusion import reciprocal_rank_fusion

logger = logging.getLogger(__name__)

class HybridSearchEngine:
    def __init__(self):
        self.repo = DocumentRepository()
        self.embedding_engine = EmbeddingEngine()
        
    def search(self, query: str, mode: str = "hybrid", top_k: int = 10, filters: dict = None) -> List[Dict]:
        start_time = time.time()
        results = []
        
        if mode == "keyword":
            results = self._search_keyword(query, top_k, filters)
        elif mode == "semantic":
            results = self._search_semantic(query, top_k, filters)
        else: # hybrid
            kw_results = self._search_keyword(query, top_k * 2, filters)
            sm_results = self._search_semantic(query, top_k * 2, filters)
            results = reciprocal_rank_fusion(kw_results, sm_results)
            results = results[:top_k]
            
        latency = (time.time() - start_time) * 1000
        logger.info(f"Search completed in {latency:.2f}ms (Mode: {mode}, Results: {len(results)})")
        return results

    def _search_keyword(self, query: str, top_k: int, filters: dict) -> List[Dict]:
        # FTS search uses SQLite virtual table
        results = self.repo.search_fts(query, top_k=top_k*2) 
        # Apply strict relational filters in Python for simplicity since FTS doesn't directly join easily in dynamic ways without complex SQL
        if filters:
            results = self._apply_filters(results, filters)
        return results[:top_k]

    def _search_semantic(self, query: str, top_k: int, filters: dict) -> List[Dict]:
        query_emb = self.embedding_engine.embed_query(query)
        
        # In a real massive DB, we'd use pgvector/sqlite-vec. Here we load all and compute via NumPy (very fast for < 100k chunks)
        all_chunks = self.repo.get_all_chunks_with_embeddings()
        if not all_chunks:
            return []
            
        # Apply filters before semantic scoring
        if filters:
            all_chunks = self._apply_filters(all_chunks, filters)
            if not all_chunks:
                return []
                
        doc_embs = np.array([deserialize_embedding(c['embedding']) for c in all_chunks])
        similarities = compute_cosine_similarity(query_emb, doc_embs)
        
        # Get top k indices
        top_indices = np.argsort(similarities)[::-1][:top_k]
        
        results = []
        for idx in top_indices:
            chunk = all_chunks[idx].copy()
            chunk['similarity'] = float(similarities[idx])
            chunk['rank_score'] = chunk['similarity'] # For RRF compatibility
            del chunk['embedding'] # Remove binary data
            results.append(chunk)
            
        return results

    def _apply_filters(self, chunks: List[Dict], filters: dict) -> List[Dict]:
        filtered = []
        for chunk in chunks:
            match = True
            for k, v in filters.items():
                if chunk.get(k) != v:
                    # check if the filter matches a field or we need to lookup document level
                    match = False
                    break
            if match:
                filtered.append(chunk)
        return filtered
