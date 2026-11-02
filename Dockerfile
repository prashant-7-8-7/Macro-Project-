# Use official lightweight Python image
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000 \
    EMBEDDING_MODEL_NAME=all-MiniLM-L6-v2

# Set work directory
WORKDIR /app

# Install minimal system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

# Copy and install python dependencies (CPU-only PyTorch to stay lightweight)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Pre-download lightweight sentence transformer model so startup is instant
RUN python -c "import os; from sentence_transformers import SentenceTransformer; SentenceTransformer(os.environ['EMBEDDING_MODEL_NAME'])"

# Copy application source code
COPY . .

# Expose server port
EXPOSE 8000

# Run FastAPI via Uvicorn with dynamic PORT support
CMD ["sh", "-c", "uvicorn src.api.routes:app --host 0.0.0.0 --port ${PORT:-8000}"]
