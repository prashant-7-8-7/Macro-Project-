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
        self.transformer_model = None
        self.fallback_model = None
        self.model_name = EMBEDDING_MODEL_NAME
        self.is_e5 = 'e5' in self.model_name.lower()
        self.use_fallback = False
        self._fallback_is_fitted = False
        self._TfidfVectorizer = None
        self._TruncatedSVD = None
        self._make_pipeline = None

        try:
            import torch
            from sentence_transformers import SentenceTransformer
            device = "cuda" if torch.cuda.is_available() else "cpu"
            logger.info(f"Loading embedding model: {self.model_name} on device: {device}...")
            self.transformer_model = SentenceTransformer(self.model_name, device=device)
            logger.info("Multilingual SentenceTransformer model loaded successfully.")
        except Exception as e:
            logger.warning(f"Failed to load sentence-transformers: {e}. Using fallback TF-IDF embeddings.")
            self._setup_fallback()

    @property
    def model(self):
        return self.transformer_model

    @model.setter
    def model(self, val):
        self.transformer_model = val

    def _setup_fallback(self):
        self.use_fallback = True
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer
            from sklearn.decomposition import TruncatedSVD
            from sklearn.pipeline import make_pipeline

            self._TfidfVectorizer = TfidfVectorizer
            self._TruncatedSVD = TruncatedSVD
            self._make_pipeline = make_pipeline

            # Script-agnostic char_wb ngram TF-IDF without English stopwords
            self.fallback_model = make_pipeline(
                TfidfVectorizer(
                    analyzer="char_wb",
                    ngram_range=(2, 4),
                    max_features=10000
                ),
                TruncatedSVD(n_components=384, random_state=42)
            )
            self._fallback_is_fitted = False
            self.dim = 384
        except Exception as e:
            logger.error(f"Fallback TF-IDF setup failed: {e}")
            self.fallback_model = None
            self.dim = 384

    def embed_texts(self, texts: List[str]) -> np.ndarray:
        """Returns a numpy array of embeddings for a list of strings."""
        if not texts:
            return np.array([])

        if not self.use_fallback and self.transformer_model is not None:
            try:
                # Add 'passage: ' prefix for e5 models
                input_texts = [f"passage: {t}" for t in texts] if self.is_e5 else texts
                embeddings = self.transformer_model.encode(input_texts, show_progress_bar=False)
                if not isinstance(embeddings, np.ndarray):
                    embeddings = embeddings.cpu().numpy()
                return embeddings
            except Exception as e:
                logger.warning(f"Error encoding with sentence-transformers: {e}. Switching to fallback.")
                self._setup_fallback()

        # Fallback path (TF-IDF / TruncatedSVD with char_wb)
        if not self.use_fallback:
            self._setup_fallback()

        if self.fallback_model is None:
            return np.zeros((len(texts), 384), dtype=np.float32)

        if not self._fallback_is_fitted:
            if self._TfidfVectorizer is None:
                from sklearn.feature_extraction.text import TfidfVectorizer
                from sklearn.decomposition import TruncatedSVD
                from sklearn.pipeline import make_pipeline
                self._TfidfVectorizer = TfidfVectorizer
                self._TruncatedSVD = TruncatedSVD
                self._make_pipeline = make_pipeline

            tfidf = self._TfidfVectorizer(
                analyzer="char_wb",
                ngram_range=(2, 4),
                max_features=10000
            )
            tfidf.fit(texts)
            n_features = len(tfidf.vocabulary_)
            n_comp = min(384, max(1, min(len(texts), n_features) - 1)) if len(texts) > 1 else 1

            self.fallback_model = self._make_pipeline(
                tfidf,
                self._TruncatedSVD(n_components=n_comp, random_state=42)
            )
            res = self.fallback_model.fit_transform(texts)

            actual_comp = min(384, res.shape[1])
            padded = np.zeros((len(texts), 384), dtype=np.float32)
            padded[:, :actual_comp] = res[:, :actual_comp]

            self._fallback_is_fitted = True
            return padded
        else:
            res = self.fallback_model.transform(texts)
            actual_comp = min(384, res.shape[1])
            padded = np.zeros((len(texts), 384), dtype=np.float32)
            padded[:, :actual_comp] = res[:, :actual_comp]
            return padded

    def embed_query(self, query: str) -> np.ndarray:
        if not self.use_fallback and self.transformer_model is not None:
            try:
                input_query = f"query: {query}" if self.is_e5 else query
                emb = self.transformer_model.encode([input_query], show_progress_bar=False)
                if not isinstance(emb, np.ndarray):
                    emb = emb.cpu().numpy()
                return emb[0]
            except Exception as e:
                logger.warning(f"Error encoding query with transformer: {e}. Switching to fallback.")
                self._setup_fallback()
        return self.embed_texts([query])[0]
