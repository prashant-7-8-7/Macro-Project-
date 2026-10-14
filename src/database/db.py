import sqlite3
from pathlib import Path
from src.config import DB_PATH
import logging

logger = logging.getLogger(__name__)

def get_connection():
    """Returns a SQLite connection with foreign keys enabled."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    # Performance pragmas
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA cache_size = -64000;") # 64MB cache
    return conn

def get_system_metadata(key: str):
    """Retrieves a system setting or metadata value."""
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("SELECT value FROM system_metadata WHERE key = ?", (key,))
        row = c.fetchone()
        return row[0] if row else None
    except Exception:
        return None
    finally:
        conn.close()

def set_system_metadata(key: str, value: str):
    """Sets a system setting or metadata value."""
    conn = get_connection()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO system_metadata (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)",
            (key, value)
        )
        conn.commit()
    finally:
        conn.close()

def migrate_db(conn: sqlite3.Connection):
    """Safely runs schema migrations on an existing SQLite database."""
    try:
        cursor = conn.cursor()
        # 1. Documents table migration: add language column
        cursor.execute("PRAGMA table_info(documents);")
        columns = [row["name"] if isinstance(row, sqlite3.Row) else row[1] for row in cursor.fetchall()]
        if "language" not in columns:
            cursor.execute("ALTER TABLE documents ADD COLUMN language TEXT DEFAULT 'en';")
            conn.commit()
            logger.info("Migrated database: added 'language' column to documents table.")

        # 2. System metadata table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS system_metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.commit()
    except Exception as e:
        logger.error(f"Error migrating database: {e}")

def init_db():
    """Initializes the database schema if not already present and detects model changes."""
    schema_path = Path(__file__).resolve().parent / "schema.sql"
    with open(schema_path, "r", encoding="utf-8") as f:
        schema_sql = f.read()
    
    conn = get_connection()
    try:
        conn.executescript(schema_sql)
        conn.commit()
        migrate_db(conn)
        logger.info("Database schema initialized successfully.")

        # Check embedding model version
        from src.config import EMBEDDING_MODEL_NAME
        last_model = get_system_metadata("embedding_model")
        if last_model and last_model != EMBEDDING_MODEL_NAME:
            logger.warning(
                f"[Model Change Detected] Active model is '{EMBEDDING_MODEL_NAME}', but DB was indexed with '{last_model}'. "
                f"Run 'python reindex.py' to re-embed existing documents with the new model."
            )
        elif not last_model:
            set_system_metadata("embedding_model", EMBEDDING_MODEL_NAME)
    except Exception as e:
        conn.rollback()
        logger.error(f"Error initializing database schema: {e}")
        raise
    finally:
        conn.close()
