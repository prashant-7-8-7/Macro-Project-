import json
import sqlite3
from typing import List, Dict, Any, Optional
from src.database.db import get_connection

class DocumentRepository:
    def __init__(self):
        pass

    def insert_document(self, doc_id: str, title: str, filename: str, file_type: str, file_size: int, doc_hash: str, metadata: dict) -> bool:
        """Inserts a new document. Returns True if inserted, False if hash already exists (duplicate)."""
        conn = get_connection()
        try:
            conn.execute(
                """
                INSERT INTO documents (id, title, filename, file_type, file_size, doc_hash, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (doc_id, title, filename, file_type, file_size, doc_hash, json.dumps(metadata))
            )
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            conn.rollback()
            return False # doc_hash is UNIQUE
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
        
    def get_all_chunks_with_embeddings(self) -> List[dict]:
        """Returns all chunks with their embeddings and parent document metadata."""
        conn = get_connection()
        cursor = conn.execute('''
            SELECT c.id, c.document_id, c.content, c.embedding, d.filename, c.page_number
            FROM document_chunks c
            JOIN documents d ON c.document_id = d.id
        ''')
        rows = [dict(r) for r in cursor.fetchall()]
        conn.close()
        return rows

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

    def search_fts(self, query: str, top_k: int = 10, document_id: str = None) -> List[dict]:
        """Performs BM25 Full-Text Search using SQLite FTS5."""
        conn = get_connection()
        # Escape query for FTS (remove quotes to prevent syntax errors)
        safe_words = [w.replace('"', '') for w in query.split() if w.strip()]
        escaped_query = ' '.join(f'"{word}"' for word in safe_words if word)
        
        if not escaped_query:
            return []
            
        if document_id:
            cursor = conn.execute("""
                SELECT c.id, c.document_id, c.content, d.filename, c.page_number, bm25(fts_chunks) as rank_score
                FROM fts_chunks f
                JOIN document_chunks c ON f.chunk_id = c.id
                JOIN documents d ON c.document_id = d.id
                WHERE fts_chunks MATCH ? AND c.document_id = ?
                ORDER BY rank_score
                LIMIT ?
            """, (escaped_query, document_id, top_k))
        else:
            cursor = conn.execute("""
                SELECT c.id, c.document_id, c.content, d.filename, c.page_number, bm25(fts_chunks) as rank_score
                FROM fts_chunks f
                JOIN document_chunks c ON f.chunk_id = c.id
                JOIN documents d ON c.document_id = d.id
                WHERE fts_chunks MATCH ?
                ORDER BY rank_score
                LIMIT ?
            """, (escaped_query, top_k))
            
        rows = [dict(r) for r in cursor.fetchall()]
        conn.close()
        return rows

    def delete_document(self, document_id: str):
        conn = get_connection()
        try:
            # ON DELETE CASCADE handles document_chunks, and trigger handles fts_chunks
            conn.execute("DELETE FROM documents WHERE id = ?", (document_id,))
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()
