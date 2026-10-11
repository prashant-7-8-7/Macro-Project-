# Use official lightweight Python image
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

# Set work directory
WORKDIR /app

# Install system dependencies (build-essential, curl, sqlite3)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

# Install PyTorch CPU-only first to prevent downloading giant multi-gigabyte CUDA binaries on Render
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

# Copy and install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download sentence transformer model during Docker build so startup is instant
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

# Copy the rest of the application code
COPY . .

# Expose server port
EXPOSE 8000

# Run FastAPI via Uvicorn
CMD ["uvicorn", "src.api.routes:app", "--host", "0.0.0.0", "--port", "8000"]
