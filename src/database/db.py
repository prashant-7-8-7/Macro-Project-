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

def migrate_db(conn: sqlite3.Connection):
    """Safely runs schema migrations on an existing SQLite database."""
    try:
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(documents);")
        columns = [row["name"] if isinstance(row, sqlite3.Row) else row[1] for row in cursor.fetchall()]
        if "language" not in columns:
            cursor.execute("ALTER TABLE documents ADD COLUMN language TEXT DEFAULT 'en';")
            conn.commit()
            logger.info("Migrated database: added 'language' column to documents table.")
    except Exception as e:
        logger.error(f"Error migrating database: {e}")

def init_db():
    """Initializes the database schema if not already present."""
    schema_path = Path(__file__).resolve().parent / "schema.sql"
    with open(schema_path, "r", encoding="utf-8") as f:
        schema_sql = f.read()
    
    conn = get_connection()
    try:
        conn.executescript(schema_sql)
        conn.commit()
        migrate_db(conn)
        logger.info("Database schema initialized successfully.")
    except Exception as e:
        conn.rollback()
        logger.error(f"Error initializing database schema: {e}")
        raise
    finally:
        conn.close()
