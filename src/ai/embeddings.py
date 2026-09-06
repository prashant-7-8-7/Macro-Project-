import logging
from typing import List, Union
import numpy as np
from src.config import EMBEDDING_MODEL_NAME

logger = logging.getLogger(__name__)

class EmbeddingEngine:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialize()
        return cls._instance
        
    def _initialize(self):
        self.model = None
        self.use_fallback = False
        try:
            from sentence_transformers import SentenceTransformer
            logger.info(f"Loading embedding model: {EMBEDDING_MODEL_NAME}...")
            self.model = SentenceTransformer(EMBEDDING_MODEL_NAME)
            logger.info("Model loaded successfully.")
        except Exception as e:
            logger.warning(f"Failed to load sentence-transformers: {e}. Using fallback TF-IDF embeddings.")
            self.use_fallback = True
            
            # Simple fallback for robust execution without PyTorch
            from sklearn.feature_extraction.text import TfidfVectorizer
            from sklearn.decomposition import TruncatedSVD
            from sklearn.pipeline import make_pipeline
            
            # Use 384 dim to match all-MiniLM-L6-v2
            self.model = make_pipeline(
                TfidfVectorizer(max_features=10000),
                TruncatedSVD(n_components=384, random_state=42)
            )
            self._fallback_is_fitted = False
            self.dim = 384

    def embed_texts(self, texts: List[str]) -> np.ndarray:
        """Returns a numpy array of embeddings for a list of strings."""
        if not texts:
            return np.array([])
            
        if self.use_fallback:
            if not self._fallback_is_fitted:
                # In real scenario, fallback requires fitting. We fit on first batch.
                from sklearn.feature_extraction.text import TfidfVectorizer
                from sklearn.decomposition import TruncatedSVD
                from sklearn.pipeline import make_pipeline
                
                tfidf = TfidfVectorizer(max_features=10000)
                tfidf.fit(texts)
                n_features = len(tfidf.vocabulary_)
                n_comp = min(384, max(1, n_features - 1))
                
                self.model = make_pipeline(
                    tfidf,
                    TruncatedSVD(n_components=n_comp, random_state=42)
                )
                res = self.model.fit_transform(texts)
                
                padded = np.zeros((len(texts), 384), dtype=np.float32)
                padded[:, :n_comp] = res
                
                self._fallback_is_fitted = True
                return padded
            else:
                res = self.model.transform(texts)
                n_comp = res.shape[1]
                padded = np.zeros((len(texts), 384), dtype=np.float32)
                padded[:, :n_comp] = res
                return padded
        else:
            # Sentence transformers returns numpy array directly or tensor
            embeddings = self.model.encode(texts, show_progress_bar=False)
            if not isinstance(embeddings, np.ndarray):
                embeddings = embeddings.cpu().numpy()
            return embeddings

    def embed_query(self, query: str) -> np.ndarray:
        return self.embed_texts([query])[0]
