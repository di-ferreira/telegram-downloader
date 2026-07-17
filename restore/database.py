import os
import json
import sqlite3

PROGRESS_DB = "restore_progress.db"


def init_progress():
    conn = sqlite3.connect(PROGRESS_DB)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS progress (
            message_id_original INTEGER PRIMARY KEY,
            message_id_novo INTEGER,
            status TEXT DEFAULT 'pending',
            data_envio TEXT,
            tentativas INTEGER DEFAULT 0,
            erro TEXT
        )
    """)
    conn.commit()
    return conn


def get_pending(conn):
    cursor = conn.execute(
        "SELECT message_id_original FROM progress WHERE status != 'sent' ORDER BY message_id_original"
    )
    return {row[0] for row in cursor.fetchall()}


def get_all_progress(conn):
    cursor = conn.execute(
        "SELECT message_id_original, status FROM progress ORDER BY message_id_original"
    )
    return dict(cursor.fetchall())


def save_progress(conn, original_id, novo_id=None, status="sent", data_envio=None, erro=None):
    conn.execute(
        """
        INSERT OR REPLACE INTO progress
        (message_id_original, message_id_novo, status, data_envio, tentativas, erro)
        VALUES (?, ?, ?, ?, COALESCE(
            (SELECT tentativas FROM progress WHERE message_id_original = ?), 0
        ) + 1, ?)
        """,
        (original_id, novo_id, status, data_envio, original_id, erro),
    )
    conn.commit()


def mark_error(conn, original_id, error_msg):
    save_progress(conn, original_id, status="error", erro=error_msg)


def resume_restore(conn):
    progress = get_all_progress(conn)
    last_sent = None
    for oid, st in progress.items():
        if st == "sent":
            last_sent = oid
    return last_sent, progress


def close_progress(conn):
    conn.close()


def load_backup(backup_folder):
    db_path = os.path.join(backup_folder, "backup.db")
    if os.path.exists(db_path):
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            "SELECT * FROM messages ORDER BY id"
        )
        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return rows

    json_path = os.path.join(backup_folder, "messages.json")
    if os.path.exists(json_path):
        with open(json_path, "r", encoding="utf-8") as f:
            return json.load(f)

    raise FileNotFoundError(
        f"No backup found in '{backup_folder}'. "
        f"Expected backup.db or messages.json."
    )


def load_messages(backup_folder):
    return load_backup(backup_folder)
