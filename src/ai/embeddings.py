import logging
import threading
from typing import List, Union
import numpy as np
from src.config import EMBEDDING_MODEL_NAME

logger = logging.getLogger(__name__)

class EmbeddingEngine:
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    instance = super().__new__(cls)
                    instance._initialize()
                    cls._instance = instance
        return cls._instance
        
    def _initialize(self):
        self.model = None
        self.use_fallback = False
        try:
            import torch
            from sentence_transformers import SentenceTransformer
            device = "cuda" if torch.cuda.is_available() else "cpu"
            logger.info(f"Loading embedding model: {EMBEDDING_MODEL_NAME} on device: {device}...")
            self.model = SentenceTransformer(EMBEDDING_MODEL_NAME, device=device)
            logger.info("Model loaded successfully.")
        except Exception as e:
            logger.warning(f"Failed to load sentence-transformers: {e}. Using fallback TF-IDF embeddings.")
            self._setup_fallback()

    def _setup_fallback(self):
        self.use_fallback = True
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer
            from sklearn.decomposition import TruncatedSVD
            from sklearn.pipeline import make_pipeline
            
            self.model = make_pipeline(
                TfidfVectorizer(max_features=10000),
                TruncatedSVD(n_components=384, random_state=42)
            )
            self._fallback_is_fitted = False
            self.dim = 384
        except Exception as e:
            logger.error(f"Fallback TF-IDF setup failed: {e}")
            self.model = None
            self.dim = 384

    def embed_texts(self, texts: List[str]) -> np.ndarray:
        """Returns a numpy array of embeddings for a list of strings."""
        if not texts:
            return np.array([])
            
        if not self.use_fallback and self.model is not None:
            try:
                embeddings = self.model.encode(texts, show_progress_bar=False)
                if not isinstance(embeddings, np.ndarray):
                    embeddings = embeddings.cpu().numpy()
                return embeddings
            except Exception as e:
                logger.warning(f"Error encoding with sentence-transformers: {e}. Switching to fallback.")
                self._setup_fallback()

        # Fallback path (TF-IDF / TruncatedSVD)
        if not self.use_fallback:
            self._setup_fallback()

        if self.model is None:
            # Emergency zero-vector if sklearn also fails
            return np.zeros((len(texts), 384), dtype=np.float32)

        if not self._fallback_is_fitted:
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

    def embed_query(self, query: str) -> np.ndarray:
        return self.embed_texts([query])[0]
