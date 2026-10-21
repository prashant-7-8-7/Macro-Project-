import time
import json
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
        self._embedding_engine = None

    @property
    def embedding_engine(self):
        if self._embedding_engine is None:
            self._embedding_engine = EmbeddingEngine()
        return self._embedding_engine
        
    def search(self, query: str, mode: str = "hybrid", top_k: int = 10, filters: dict = None) -> List[Dict]:
        start_time = time.time()
        if mode not in {"keyword", "semantic", "hybrid"}:
            raise ValueError("Search mode must be keyword, semantic, or hybrid")
        if not query.strip() or not 1 <= top_k <= 50:
            raise ValueError("Provide a query and top_k between 1 and 50")
        results = []
        
        if mode == "keyword":
            results = self._search_keyword(query, top_k, filters)
        elif mode == "semantic":
            results = self._search_semantic(query, top_k, filters)
        else: # hybrid
            kw_results = self._search_keyword(query, top_k * 2, filters)
            try:
                sm_results = self._search_semantic(query, top_k * 2, filters)
            except Exception as exc:
                logger.warning('Semantic retrieval unavailable (%s); keyword results remain usable.', type(exc).__name__)
                sm_results = []
            results = reciprocal_rank_fusion(kw_results, sm_results)
            results = results[:top_k]
            
        latency = (time.time() - start_time) * 1000
        logger.info(f"Search completed in {latency:.2f}ms (Mode: {mode}, Results: {len(results)})")
        return results

    def _search_keyword(self, query: str, top_k: int, filters: dict) -> List[Dict]:
        # FTS search uses SQLite virtual table
        return self.repo.search_fts(query, top_k=top_k, filters=filters)

    def _search_semantic(self, query: str, top_k: int, filters: dict) -> List[Dict]:
        # In a real massive DB, we'd use pgvector/sqlite-vec. Here we load all and compute via NumPy (very fast for < 100k chunks)
        all_chunks = self.repo.get_all_chunks_with_embeddings(filters=filters)
        if not all_chunks:
            return []
            
        query_emb = self.embedding_engine.embed_query(query)
        engine = self.embedding_engine
        compatible = []
        for chunk in all_chunks:
            metadata = json.loads(chunk.get('metadata_json') or '{}')
            profile = metadata.get('embedding_backend')
            if profile == engine.profile and len(chunk['embedding']) == query_emb.size * 4:
                compatible.append(chunk)
        all_chunks = compatible
        if not all_chunks:
            logger.warning('No compatible embeddings in this scope; run python reindex.py for the active backend.')
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
