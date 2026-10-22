import json
import sqlite3
from typing import List, Dict, Any, Optional, Tuple
from src.database.db import get_connection
from src.retrieval.query import topic_terms

class DocumentRepository:
    _migrated = False

    def __init__(self):
        if not DocumentRepository._migrated:
            try:
                conn = get_connection()
                from src.database.db import migrate_db
                migrate_db(conn)
                conn.close()
                DocumentRepository._migrated = True
            except Exception:
                pass

    def insert_document(self, doc_id: str, title: str, filename: str, file_type: str, file_size: int, doc_hash: str, metadata: dict, language: str = 'en') -> bool:
        """Inserts a new document with detected language. Returns True if inserted, False if hash already exists (duplicate)."""
        conn = get_connection()
        try:
            conn.execute(
                """
                INSERT INTO documents (id, title, filename, file_type, file_size, doc_hash, language, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (doc_id, title, filename, file_type, file_size, doc_hash, language, json.dumps(metadata))
            )
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            conn.rollback()
            return False # doc_hash is UNIQUE
        finally:
            conn.close()

    def update_document_language(self, doc_id: str, language: str):
        conn = get_connection()
        try:
            conn.execute("UPDATE documents SET language = ? WHERE id = ?", (language, doc_id))
            conn.commit()
        finally:
            conn.close()

    def insert_document_with_chunks(self, *, chunks: List[Dict[str, Any]], **document) -> bool:
        """Commit the document, chunks, and FTS entries together, or roll all back."""
        conn = get_connection()
        try:
            with conn:
                cursor = conn.execute(
                    """INSERT INTO documents
                    (id, title, filename, file_type, file_size, doc_hash, language, metadata_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(doc_hash) DO NOTHING""",
                    (document["doc_id"], document["title"], document["filename"],
                     document["file_type"], document["file_size"], document["doc_hash"],
                     document.get("language", "en"), json.dumps(document.get("metadata", {}))),
                )
                if cursor.rowcount == 0:
                    return False
                conn.executemany(
                    """INSERT INTO document_chunks
                    (id, document_id, chunk_index, content, token_count, page_number, embedding)
                    VALUES (:id, :document_id, :chunk_index, :content, :token_count, :page_number, :embedding)""",
                    chunks,
                )
                for page in document.get('pages', []):
                    if page.get('ocr_words'):
                        conn.execute('INSERT INTO document_ocr VALUES (?,?,?)',
                                     (document['doc_id'], page['page_number'], json.dumps(page['ocr_words'])))
            return True
        finally:
            conn.close()

    def get_document(self, document_id: str) -> Optional[dict]:
        conn = get_connection()
        try:
            row = conn.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()
            
    def get_document_by_hash(self, doc_hash: str) -> Optional[dict]:
        conn = get_connection()
        cursor = conn.execute("SELECT * FROM documents WHERE doc_hash = ?", (doc_hash,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    def insert_chunks(self, chunks: List[Dict[str, Any]]):
        """Batch inserts document chunks."""
        conn = get_connection()
        try:
            conn.executemany(
                """
                INSERT INTO document_chunks (id, document_id, chunk_index, content, token_count, page_number, embedding)
                VALUES (:id, :document_id, :chunk_index, :content, :token_count, :page_number, :embedding)
                """,
                chunks
            )
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()

    def update_chunk_embeddings(self, chunk_updates: List[Tuple[bytes, str]], profile: Optional[str] = None):
        """Batch updates embeddings for existing chunks: list of (embedding_blob, chunk_id)."""
        conn = get_connection()
        try:
            conn.executemany(
                "UPDATE document_chunks SET embedding = ? WHERE id = ?",
                chunk_updates
            )
            if profile:
                documents = {row[0] for _, chunk_id in chunk_updates for row in conn.execute('SELECT document_id FROM document_chunks WHERE id=?', (chunk_id,))}
                for ident in documents:
                    row = conn.execute('SELECT metadata_json FROM documents WHERE id=?', (ident,)).fetchone()
                    metadata = json.loads(row[0]); metadata['embedding_backend'] = profile
                    conn.execute('UPDATE documents SET metadata_json=? WHERE id=?', (json.dumps(metadata), ident))
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()
            
    def get_all_documents(self) -> List[dict]:
        conn = get_connection()
        cursor = conn.execute("SELECT * FROM documents ORDER BY created_at DESC")
        rows = [dict(r) for r in cursor.fetchall()]
        conn.close()
        return rows

    def get_document_chunks(self, document_id: str) -> List[dict]:
        conn = get_connection()
        cursor = conn.execute("SELECT * FROM document_chunks WHERE document_id = ? ORDER BY chunk_index", (document_id,))
        rows = [dict(r) for r in cursor.fetchall()]
        conn.close()
        return rows
        
    def get_all_chunks_with_embeddings(self, filters: Optional[dict] = None) -> List[dict]:
        """Returns all chunks with their embeddings and parent document metadata."""
        where, params = self._filter_sql(filters)
        conn = get_connection()
        try:
            cursor = conn.execute('''
                SELECT c.id, c.document_id, c.chunk_index, c.content, c.embedding,
                       d.filename, d.file_type, d.language, d.metadata_json, c.page_number
                FROM document_chunks c
                JOIN documents d ON c.document_id = d.id
            ''' + where, params)
            return [dict(r) for r in cursor.fetchall()]
        finally:
            conn.close()

    def get_document_chunks_content(self, document_id: str) -> List[dict]:
        """Returns ordered chunks for a document to reconstruct text."""
        conn = get_connection()
        cursor = conn.execute(
            "SELECT chunk_index, content, page_number FROM document_chunks WHERE document_id = ? ORDER BY chunk_index",
            (document_id,)
        )
        rows = [dict(r) for r in cursor.fetchall()]
        conn.close()
        return rows

    @staticmethod
    def _filter_sql(filters: Optional[dict], conjunction: str = "WHERE") -> Tuple[str, list]:
        columns = {"document_id": "c.document_id", "filename": "d.filename",
                   "file_type": "d.file_type", "language": "d.language",
                   "page_number": "c.page_number"}
        filters = filters or {}
        scoped_ids = filters.get('document_ids')
        filters = {key: value for key, value in filters.items() if key != 'document_ids'}
        unknown = set(filters) - columns.keys()
        if unknown:
            raise ValueError("Unsupported search filter: " + ", ".join(sorted(unknown)))
        clauses = [f"{columns[key]} = ?" for key in filters]
        params = list(filters.values())
        if scoped_ids is not None:
            clauses.append('c.document_id IN (' + ','.join('?' for _ in scoped_ids) + ')' if scoped_ids else '0=1')
            params.extend(scoped_ids)
        return (f" {conjunction} " + " AND ".join(clauses), params) if clauses else ("", [])

    def search_fts(self, query: str, top_k: int = 10, document_id: str = None,
                   filters: Optional[dict] = None) -> List[dict]:
        """Performs BM25 Full-Text Search using SQLite FTS5."""
        words = topic_terms(query)
        if not words:
            return []
        scoped_filters = dict(filters or {})
        if document_id is not None:
            scoped_filters["document_id"] = document_id
        where, params = self._filter_sql(scoped_filters, "AND")
        conn = get_connection()
        try:
            sql = """
                SELECT c.id, c.document_id, c.chunk_index, c.content, d.filename,
                       d.file_type, d.language, c.page_number, bm25(fts_chunks) as rank_score
                FROM fts_chunks f
                JOIN document_chunks c ON f.chunk_id = c.id
                JOIN documents d ON c.document_id = d.id
                WHERE fts_chunks MATCH ?
            """ + where + """
                ORDER BY rank_score
                LIMIT ?
            """
            # Prefer chunks containing every topic term. If none match, relax
            # to any topic term; natural questions need not occur verbatim.
            for operator in (' AND ', ' OR '):
                expression = operator.join(f'"{word}"' for word in words)
                rows = [dict(r) for r in conn.execute(sql, [expression, *params, top_k])]
                if rows:
                    return rows
            return []
        finally:
            conn.close()

    def context_chunks(self, chunk_ids: List[str], filters: Optional[dict] = None) -> List[dict]:
        """Read at most 50 cited/sampled chunks, still enforcing document scope."""
        ids = list(dict.fromkeys(chunk_ids))[:50]
        if not ids:
            return []
        where, params = self._filter_sql(filters, 'AND')
        conn = get_connection()
        try:
            rows = conn.execute('''
                SELECT c.id, c.document_id, c.chunk_index, c.content, c.page_number,
                       d.filename, d.file_type, d.language, 0.0 AS rank_score
                FROM document_chunks c JOIN documents d ON c.document_id = d.id
                WHERE c.id IN (''' + ','.join('?' for _ in ids) + ')' + where, [*ids, *params])
            by_id = {row['id']: dict(row) for row in rows}
            return [by_id[ident] for ident in ids if ident in by_id]
        finally:
            conn.close()

    def representative_chunks(self, filters: Optional[dict] = None, top_k: int = 6) -> List[dict]:
        """Sample actual document text for topic-free overview requests only."""
        if not 1 <= top_k <= 50:
            raise ValueError('top_k must be between 1 and 50')
        where, params = self._filter_sql(filters)
        conn = get_connection()
        try:
            # Read only IDs while selecting samples, not every text/vector blob.
            rows = conn.execute('''
                SELECT c.id, c.document_id FROM document_chunks c
                JOIN documents d ON c.document_id = d.id
            ''' + where + ' ORDER BY c.document_id, c.chunk_index', params)
            grouped = {}
            for row in rows:
                grouped.setdefault(row['document_id'], []).append(row['id'])
        finally:
            conn.close()
        if not grouped:
            return []
        quotas = {ident: 0 for ident in grouped}
        remaining = top_k
        while remaining:
            added = False
            for ident, ids in grouped.items():
                if remaining and quotas[ident] < len(ids):
                    quotas[ident] += 1
                    remaining -= 1
                    added = True
            if not added:
                break
        samples = []
        for ident, ids in grouped.items():
            count = quotas[ident]
            samples.append([ids[i * (len(ids) - 1) // (count - 1)] if count > 1 else ids[0]
                            for i in range(count)])
        selected = [ids[i] for i in range(max(quotas.values())) for ids in samples if i < len(ids)]
        return self.context_chunks(selected, filters)

    def delete_document(self, document_id: str):
        original = self.get_document(document_id)
        conn = get_connection()
        try:
            # ON DELETE CASCADE handles document_chunks, and trigger handles fts_chunks
            conn.execute("DELETE FROM documents WHERE id = ?", (document_id,))
            conn.commit()
            if original:
                from src.ingestion.ocr import original_path
                original_path(original).unlink(missing_ok=True)
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()

    # Notes Section Caching for Map-Reduce Scaling
    def get_cached_note_section(
        self, document_id: str, section_index: int, detail_level: str, language: str
    ) -> Optional[dict]:
        """Fetches a previously processed section note from cache."""
        conn = get_connection()
        try:
            cursor = conn.execute(
                """
                SELECT content_json FROM notes_section_cache
                WHERE document_id = ? AND section_index = ? AND detail_level = ? AND language = ?
                """,
                (document_id, section_index, detail_level, language)
            )
            row = cursor.fetchone()
            if row:
                return json.loads(row["content_json"])
            return None
        finally:
            conn.close()

    def set_cached_note_section(
        self, document_id: str, section_index: int, detail_level: str, language: str, content: dict
    ):
        """Caches a finished section note keyed by document id + section + detail level + language."""
        conn = get_connection()
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO notes_section_cache (document_id, section_index, detail_level, language, content_json, created_at)
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                (document_id, section_index, detail_level, language, json.dumps(content))
            )
            conn.commit()
        finally:
            conn.close()

    def get_all_cached_note_sections(
        self, document_id: str, detail_level: str, language: str
    ) -> Dict[int, dict]:
        """Fetches all cached section notes for a document at given detail level and language."""
        conn = get_connection()
        try:
            cursor = conn.execute(
                """
                SELECT section_index, content_json FROM notes_section_cache
                WHERE document_id = ? AND detail_level = ? AND language = ?
                ORDER BY section_index ASC
                """,
                (document_id, detail_level, language)
            )
            return {r["section_index"]: json.loads(r["content_json"]) for r in cursor.fetchall()}
        finally:
            conn.close()

    def clear_note_sections_cache(
        self, document_id: str, detail_level: Optional[str] = None, language: Optional[str] = None
    ):
        """Clears cached sections for a document, optionally scoped to detail level and language."""
        conn = get_connection()
        try:
            if detail_level and language:
                conn.execute(
                    "DELETE FROM notes_section_cache WHERE document_id = ? AND detail_level = ? AND language = ?",
                    (document_id, detail_level, language)
                )
            elif detail_level:
                conn.execute(
                    "DELETE FROM notes_section_cache WHERE document_id = ? AND detail_level = ?",
                    (document_id, detail_level)
                )
            else:
                conn.execute("DELETE FROM notes_section_cache WHERE document_id = ?", (document_id,))
            conn.commit()
        finally:
            conn.close()

