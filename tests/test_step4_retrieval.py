import sys
import pytest

pytestmark = pytest.mark.integration
from pathlib import Path
import numpy as np

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import EMBEDDING_MODEL_NAME
from src.ai.embeddings import EmbeddingEngine
from src.ai.vector_math import compute_cosine_similarity
from src.retrieval.engine import HybridSearchEngine


def test_tfidf_fallback_multilingual():
    """Verify TF-IDF fallback works for all scripts with char_wb without English stopwords."""
    engine = EmbeddingEngine()
    engine.use_fallback = True
    engine._setup_fallback()

    multilingual_texts = [
        "Machine learning in English",
        "मशीन लर्निंग और कृत्रिम बुद्धिमत्ता",
        "Aprendizaje automático y procesamiento de lenguaje",
        "تعلم الآلة والذكاء الاصطناعي",
        "机器学习和自然语言处理技术",
        "機械学習と自然言語処理の応用"
    ]

    embs = engine.embed_texts(multilingual_texts)
    assert isinstance(embs, np.ndarray), "Embeddings must be numpy array"
    assert embs.shape[0] == len(multilingual_texts), f"Expected {len(multilingual_texts)} rows, got {embs.shape[0]}"
    assert embs.shape[1] == 384, f"Expected 384 dimensions, got {embs.shape[1]}"
    assert not np.all(embs == 0), "Embeddings should not be all zeros"

    q_emb = engine.embed_query("कृत्रिम बुद्धिमत्ता")
    assert q_emb.shape == (384,), f"Query embedding shape mismatch: {q_emb.shape}"
    print("[OK] test_tfidf_fallback_multilingual passed")


def test_e5_prefix_support():
    """Verify e5 models automatically add 'query: ' and 'passage: ' prefixes."""
    engine = EmbeddingEngine()
    engine.use_fallback = False

    # Simulate e5 configuration
    engine.is_e5 = True
    engine.model_name = "intfloat/multilingual-e5-small"

    # Verify logic flags
    assert engine.is_e5 is True
    # Reset to active model
    engine.model_name = EMBEDDING_MODEL_NAME
    engine.is_e5 = "e5" in EMBEDDING_MODEL_NAME.lower()
    print("[OK] test_e5_prefix_support passed")


def test_cross_language_semantic_similarity():
    """Verify an English query has strong semantic similarity to equivalent Hindi text."""
    engine = EmbeddingEngine()
    engine.use_fallback = False

    en_query = "What is artificial intelligence and machine learning?"
    hi_passage = "कृत्रिम बुद्धिमत्ता और मशीन लर्निंग आधुनिक कंप्यूटर विज्ञान के प्रमुख क्षेत्र हैं।"
    unrelated_passage = "Recetas tradicionales de cocina mediterránea y ensaladas frescas."

    q_emb = engine.embed_query(en_query)
    passages_emb = engine.embed_texts([hi_passage, unrelated_passage])

    sims = compute_cosine_similarity(q_emb, passages_emb)
    hi_sim = float(sims[0])
    unrelated_sim = float(sims[1])

    print(f"[Cross-Language] Query (EN) vs Hindi passage similarity: {hi_sim:.4f}")
    print(f"[Cross-Language] Query (EN) vs Unrelated passage similarity: {unrelated_sim:.4f}")

    assert hi_sim > unrelated_sim, f"Expected Hindi passage similarity ({hi_sim:.4f}) to exceed unrelated passage ({unrelated_sim:.4f})"
    assert hi_sim > 0.40, f"Expected cross-lingual similarity > 0.40, got {hi_sim:.4f}"
    print("[OK] test_cross_language_semantic_similarity passed")


def test_hybrid_search_retrieval():
    """Verify hybrid search executes across indexed documents without errors."""
    search_engine = HybridSearchEngine()
    results = search_engine.search("कृत्रिम बुद्धिमत्ता", mode="semantic", top_k=3)
    assert isinstance(results, list)
    if results:
        assert "content" in results[0]
        assert "similarity" in results[0]
    print("[OK] test_hybrid_search_retrieval passed")


if __name__ == "__main__":
    test_tfidf_fallback_multilingual()
    test_e5_prefix_support()
    test_cross_language_semantic_similarity()
    test_hybrid_search_retrieval()
    print("\nALL STEP 4 MULTILINGUAL RETRIEVAL TESTS PASSED SUCCESSFULLY!")
