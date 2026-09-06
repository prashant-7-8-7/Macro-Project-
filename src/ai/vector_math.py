import numpy as np

def serialize_embedding(embedding: np.ndarray) -> bytes:
    """Serializes a numpy array to bytes for SQLite BLOB storage."""
    return embedding.astype(np.float32).tobytes()

def deserialize_embedding(blob: bytes) -> np.ndarray:
    """Deserializes SQLite BLOB to a numpy array."""
    return np.frombuffer(blob, dtype=np.float32)

def compute_cosine_similarity(query_emb: np.ndarray, doc_embs: np.ndarray) -> np.ndarray:
    """
    Computes cosine similarity between a query vector and a matrix of document vectors.
    Returns 1D array of similarity scores.
    """
    # L2 normalize query
    query_norm = np.linalg.norm(query_emb)
    if query_norm > 0:
        query_emb = query_emb / query_norm
        
    # L2 normalize docs
    doc_norms = np.linalg.norm(doc_embs, axis=1, keepdims=True)
    # Prevent division by zero
    doc_norms[doc_norms == 0] = 1e-10
    doc_embs_normalized = doc_embs / doc_norms
    
    # Dot product is cosine similarity for normalized vectors
    similarities = np.dot(doc_embs_normalized, query_emb)
    return similarities
