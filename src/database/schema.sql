-- Master Documents Table
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    filename TEXT NOT NULL,
    file_type TEXT NOT NULL,
    file_size INTEGER NOT NULL,
    doc_hash TEXT UNIQUE NOT NULL,
    metadata_json TEXT DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Document Chunks Table
CREATE TABLE IF NOT EXISTS document_chunks (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    token_count INTEGER NOT NULL,
    page_number INTEGER DEFAULT 1,
    embedding BLOB NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (document_id) REFERENCES documents (id) ON DELETE CASCADE
);

-- Full-Text Search Virtual Table (FTS5) for BM25 Keyword Search
CREATE VIRTUAL TABLE IF NOT EXISTS fts_chunks USING fts5(
    chunk_id UNINDEXED,
    document_id UNINDEXED,
    content,
    tokenize = 'porter unicode61'
);

-- Search & Retrieval Audit Log
CREATE TABLE IF NOT EXISTS queries_log (
    id TEXT PRIMARY KEY,
    query_text TEXT NOT NULL,
    search_mode TEXT NOT NULL,
    filters_json TEXT DEFAULT '{}',
    top_k INTEGER NOT NULL,
    results_count INTEGER NOT NULL,
    latency_ms REAL NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for Relational Performance
CREATE INDEX IF NOT EXISTS idx_chunks_doc_id ON document_chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_docs_file_type ON documents(file_type);
CREATE INDEX IF NOT EXISTS idx_docs_created ON documents(created_at);

-- Triggers for FTS sync (Insert, Delete, Update)
CREATE TRIGGER IF NOT EXISTS fts_chunks_ai AFTER INSERT ON document_chunks BEGIN
  INSERT INTO fts_chunks(chunk_id, document_id, content) VALUES (new.id, new.document_id, new.content);
END;

CREATE TRIGGER IF NOT EXISTS fts_chunks_ad AFTER DELETE ON document_chunks BEGIN
  DELETE FROM fts_chunks WHERE chunk_id = old.id;
END;

CREATE TRIGGER IF NOT EXISTS fts_chunks_au AFTER UPDATE ON document_chunks BEGIN
  DELETE FROM fts_chunks WHERE chunk_id = old.id;
  INSERT INTO fts_chunks(chunk_id, document_id, content) VALUES (new.id, new.document_id, new.content);
END;
