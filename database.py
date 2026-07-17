import sqlite3
import os
from config import OUTPUT_DIR

DB_PATH = os.path.join(OUTPUT_DIR, "backup.db")

def init_sync():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY,
            date TEXT,
            text TEXT,
            sender_id INTEGER,
            sender_name TEXT,
            message_type TEXT,
            views INTEGER,
            media_path TEXT,
            media_type TEXT,
            file_name TEXT,
            file_size INTEGER,
            mime_type TEXT,
            md5_hash TEXT
        )
    """)
    conn.commit()
    return conn

def message_exists(conn, msg_id):
    cursor = conn.execute("SELECT 1 FROM messages WHERE id = ?", (msg_id,))
    return cursor.fetchone() is not None

def insert_message(conn, data):
    conn.execute("""
        INSERT OR REPLACE INTO messages
        (id, date, text, sender_id, sender_name, message_type, views,
         media_path, media_type, file_name, file_size, mime_type, md5_hash)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        data["id"], data["date"], data["text"],
        data.get("sender_id"), data.get("sender_name"),
        data["message_type"], data.get("views"),
        data.get("media_path"), data.get("media_type"),
        data.get("file_name"), data.get("file_size"),
        data.get("mime_type"), data.get("md5_hash")
    ))
    conn.commit()

def get_last_id(conn):
    cursor = conn.execute("SELECT MAX(id) FROM messages")
    row = cursor.fetchone()
    return row[0] if row[0] else 0

def get_media_map(conn):
    cursor = conn.execute("SELECT media_path, md5_hash FROM messages WHERE media_path NOT NULL")
    return {row[0]: row[1] for row in cursor.fetchall()}

def close(conn):
    conn.close()
