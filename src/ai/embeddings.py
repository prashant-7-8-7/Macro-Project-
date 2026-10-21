import logging
import os
import threading
from typing import List
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
        try:
            import torch
            from sentence_transformers import SentenceTransformer
            device = os.environ.get('EMBEDDING_DEVICE') or ('cuda' if torch.cuda.is_available() else 'cpu')
            self.transformer_model = SentenceTransformer(self.model_name, device=device)
        except Exception as exc:
            logger.warning('Transformer unavailable (%s); using deterministic lexical vectors. Reindex legacy vectors before using this backend.', type(exc).__name__)
            self._setup_fallback()

    @property
    def profile(self):
        return 'hashing-char-384-v1' if self.use_fallback else 'transformer:' + self.model_name

    @property
    def model(self):
        return self.transformer_model

    @model.setter
    def model(self, value):
        self.transformer_model = value

    def _setup_fallback(self):
        from sklearn.feature_extraction.text import HashingVectorizer
        self.use_fallback = True
        self.fallback_model = HashingVectorizer(analyzer='char_wb', ngram_range=(2, 4),
                                               n_features=384, alternate_sign=False, norm='l2')
        self._fallback_is_fitted = True
        self.dim = 384

    def embed_texts(self, texts: List[str]) -> np.ndarray:
        if not texts:
            return np.empty((0, 384), dtype=np.float32)
        if self.use_fallback:
            return self.fallback_model.transform(texts).toarray().astype(np.float32)
        if self.transformer_model is None:
            self._setup_fallback()
            return self.embed_texts(texts)
        inputs = [f'passage: {text}' for text in texts] if self.is_e5 else texts
        # Encoding errors do not silently change the vector space of an existing index.
        return np.asarray(self.transformer_model.encode(inputs, show_progress_bar=False), dtype=np.float32)

    def embed_query(self, query: str) -> np.ndarray:
        if self.use_fallback:
            return self.embed_texts([query])[0]
        if self.transformer_model is None:
            self._setup_fallback()
            return self.embed_query(query)
        text = f'query: {query}' if self.is_e5 else query
        return np.asarray(self.transformer_model.encode([text], show_progress_bar=False), dtype=np.float32)[0]
