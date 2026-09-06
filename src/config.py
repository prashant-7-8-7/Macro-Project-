import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "documents.db"
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploads"

# Ensure directories exist
DATA_DIR.mkdir(exist_ok=True)
UPLOAD_DIR.mkdir(exist_ok=True)

# Chunking settings
CHUNK_SIZE = 500
CHUNK_OVERLAP = 50

# Embedding settings
EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"
