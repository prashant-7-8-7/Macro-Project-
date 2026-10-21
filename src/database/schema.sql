-- Master Documents Table
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    filename TEXT NOT NULL,
    file_type TEXT NOT NULL,
    file_size INTEGER NOT NULL,
    doc_hash TEXT UNIQUE NOT NULL,
    language TEXT DEFAULT 'en',
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

-- System Settings & Model Version Tracking
CREATE TABLE IF NOT EXISTS system_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Notes Section Cache for Resilient Background Map-Reduce
CREATE TABLE IF NOT EXISTS notes_section_cache (
    document_id TEXT NOT NULL,
    section_index INTEGER NOT NULL,
    detail_level TEXT NOT NULL,
    language TEXT NOT NULL,
    content_json TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (document_id, section_index, detail_level, language),
    FOREIGN KEY (document_id) REFERENCES documents (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_notes_cache_doc ON notes_section_cache (document_id);

-- Persistent study workflow. Existing document/chunk tables stay compatible.
CREATE TABLE IF NOT EXISTS collections (
 id TEXT PRIMARY KEY, name TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS collection_documents (
 collection_id TEXT REFERENCES collections(id) ON DELETE CASCADE,
 document_id TEXT REFERENCES documents(id) ON DELETE CASCADE,
 PRIMARY KEY(collection_id, document_id)
);
CREATE TABLE IF NOT EXISTS chat_sessions (
 id TEXT PRIMARY KEY, document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
 scope_json TEXT NOT NULL, title TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP,
 updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS chat_messages (
 id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
 role TEXT NOT NULL CHECK(role IN ('user','assistant')), content TEXT NOT NULL,
 citations_json TEXT NOT NULL DEFAULT '[]', created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_chat_messages_session ON chat_messages(session_id, created_at);
CREATE TABLE IF NOT EXISTS study_quizzes (
 id TEXT PRIMARY KEY, document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
 questions_json TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS quiz_attempts (
 id TEXT PRIMARY KEY, quiz_id TEXT NOT NULL REFERENCES study_quizzes(id) ON DELETE CASCADE,
 answers_json TEXT NOT NULL, correct INTEGER NOT NULL, total INTEGER NOT NULL,
 created_at TEXT DEFAULT CURRENT_TIMESTAMP, UNIQUE(quiz_id)
);
CREATE TABLE IF NOT EXISTS flashcards (
 id TEXT PRIMARY KEY, document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
 question TEXT NOT NULL, answer TEXT NOT NULL, source_page INTEGER, source_chunk_id TEXT,
 source_quote TEXT, interval_days INTEGER NOT NULL DEFAULT 0, repetitions INTEGER NOT NULL DEFAULT 0,
 due_at TEXT NOT NULL, updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
 UNIQUE(document_id, question, answer)
);
CREATE INDEX IF NOT EXISTS idx_flashcards_due ON flashcards(due_at);
CREATE TABLE IF NOT EXISTS notes_versions (
 id TEXT PRIMARY KEY, document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
 label TEXT NOT NULL, notes_json TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS document_ocr (
 document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
 page_number INTEGER NOT NULL, words_json TEXT NOT NULL,
 PRIMARY KEY(document_id, page_number)
);
CREATE TABLE IF NOT EXISTS ai_response_cache (
 cache_key TEXT PRIMARY KEY, response TEXT NOT NULL, created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS ai_daily_usage (
 provider TEXT NOT NULL, day TEXT NOT NULL, requests INTEGER NOT NULL DEFAULT 0,
 blocked_until INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(provider, day)
);
