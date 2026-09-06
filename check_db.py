import os
import sqlite3
from src.database.db import get_connection

conn = get_connection()
docs = conn.execute("SELECT id, filename FROM documents").fetchall()
print("Documents in DB:")
for d in docs:
    print(dict(d))

conn.close()
