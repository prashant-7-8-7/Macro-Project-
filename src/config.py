import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.environ.get("DB_PATH", str(BASE_DIR / "documents.db")))
DATA_DIR = Path(os.environ.get("DATA_DIR", str(BASE_DIR / "data")))
UPLOAD_DIR = DATA_DIR / "uploads"

# Ensure directories exist
DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

MAX_UPLOAD_BYTES = int(os.environ.get("MAX_UPLOAD_MB", "25")) * 1024 * 1024
ALLOWED_EXTENSIONS = {".pdf", ".txt", ".md", ".docx", ".csv", ".json"}

# Chunking settings
CHUNK_SIZE = 500
CHUNK_OVERLAP = 50

# Embedding settings (multilingual by default, configurable via env var)
EMBEDDING_MODEL_NAME = os.environ.get("EMBEDDING_MODEL_NAME", "paraphrase-multilingual-MiniLM-L12-v2")
