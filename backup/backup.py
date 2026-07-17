import os
import sys
import re
import json
import csv
import asyncio
import hashlib
import logging
import argparse
from datetime import datetime
from pathlib import Path

from telethon import TelegramClient
from telethon.errors import FloodWaitError
from telethon.tl.types import (
    MessageMediaPhoto, MessageMediaDocument, MessageMediaWebPage,
    Message, PeerChannel
)
from tqdm.asyncio import tqdm as async_tqdm
from tqdm import tqdm

from config import API_ID, API_HASH, CHANNEL, OUTPUT_DIR, CONCURRENT_DOWNLOADS, SESSION_NAME, validate
import database as db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(OUTPUT_DIR, "log.txt"), encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)
log = logging.getLogger(__name__)

MEDIA_DIRS = {
    "photo": "photos",
    "video": "videos",
    "document": "documents",
    "audio": "audios",
    "gif": "gifs",
    "sticker": "stickers",
}

client = None
semaphore = None
start_time = None

def create_folders():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    for folder in set(MEDIA_DIRS.values()):
        os.makedirs(os.path.join(OUTPUT_DIR, "media", folder), exist_ok=True)
    os.makedirs(os.path.join(OUTPUT_DIR, "media", "others"), exist_ok=True)

async def login():
    global client
    client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
    await client.start()
    me = await client.get_me()
    log.info(f"Logged in as {me.username or me.first_name} (ID: {me.id})")
    return client

def get_media_category(media):
    if not media:
        return None, None
    if hasattr(media, "sticker"):
        return "sticker", "sticker"
    if hasattr(media, "photo") or isinstance(media, MessageMediaPhoto):
        return "photo", "photo"
    if isinstance(media, MessageMediaDocument):
        doc = media.document
        mime = doc.mime_type or ""
        if mime.startswith("video"):
            if getattr(doc, "attributes", None):
                for attr in doc.attributes:
                    if hasattr(attr, "round_message") and attr.round_message:
                        return "video", "video"
            return "video", "video"
        if mime.startswith("audio"):
            return "audio", "audio"
        if mime == "image/gif" or (getattr(doc, "attributes", None) and any(
            hasattr(a, "supports_streaming") and hasattr(a, "duration") for a in doc.attributes
        ) and mime == "image/gif"):
            return "gif", "gif"
        if mime == "application/x-tgsticker":
            return "sticker", "sticker"
        ext = os.path.splitext(getattr(doc, "filename", "") or "")[1].lower()
        if ext in (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".zip", ".rar", ".7z", ".tar", ".gz"):
            return "document", "document"
        return "document", "document"
    return None, None

def get_file_name(message, media, media_type):
    if not media:
        return None

    text = message.text or message.message or ""
    tag = extract_hashtag(text)
    if tag:
        ext = get_extension(media, media_type)
        return f"{tag}{ext}"

    if media_type == "sticker":
        ext = get_extension(media, media_type)
        return f"sticker_{message.id}{ext}"
    if hasattr(media, "document") and media.document:
        doc = media.document
        for attr in doc.attributes:
            if hasattr(attr, "file_name") and attr.file_name:
                fname = attr.file_name
                name_part = fname.replace("\\", "/").split("/")[-1]
                if name_part:
                    return name_part
                return fname
        ext = get_extension(media, media_type)
        if ext:
            return f"{media_type}_{message.id}{ext}"
        return f"{media_type}_{message.id}"
    if hasattr(media, "photo") or isinstance(media, MessageMediaPhoto):
        return f"photo_{message.id}.jpg"
    return f"{media_type}_{message.id}"

def get_media_path(media_type):
    folder = MEDIA_DIRS.get(media_type, "others")
    return os.path.join(OUTPUT_DIR, "media", folder)

def compute_md5(file_path):
    if not os.path.exists(file_path):
        return None
    h = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def extract_hashtag(text):
    if not text:
        return None
    match = re.search(r"#(\w+)", text)
    if match:
        return match.group(1)
    return None


def get_extension(media, media_type):
    if media_type == "sticker":
        if hasattr(media, "document") and media.document:
            mime = media.document.mime_type or ""
            ext_map = {"image/webp": ".webp", "image/png": ".png", "application/x-tgsticker": ".tgs"}
            return ext_map.get(mime, ".webp")
        return ".webp"
    if media_type == "photo" or (hasattr(media, "photo") or isinstance(media, type(None)) == False and hasattr(media, "photo")):
        return ".jpg"
    if hasattr(media, "document") and media.document:
        mime = media.document.mime_type or ""
        ext_map = {
            "video/mp4": ".mp4", "video/avi": ".avi", "video/mkv": ".mkv",
            "video/quicktime": ".mov", "video/x-msvideo": ".avi",
            "audio/mpeg": ".mp3", "audio/ogg": ".ogg", "audio/mp4": ".m4a",
            "audio/wav": ".wav", "audio/aac": ".aac", "audio/flac": ".flac",
            "image/jpeg": ".jpg", "image/png": ".png", "image/gif": ".gif",
            "image/webp": ".webp", "application/pdf": ".pdf",
            "application/zip": ".zip", "application/x-rar": ".rar",
            "application/x-7z-compressed": ".7z", "application/gzip": ".tar.gz",
        }
        for m, ext in ext_map.items():
            if mime.startswith(m.split("/")[0]) and mime == m:
                return ext
        if mime.startswith("video/"):
            return ".mp4"
        if mime.startswith("audio/"):
            return ".mp3"
        if mime.startswith("image/"):
            return ".jpg"
    return ""

async def download_media(message, media, media_type, skip_existing, existing_media):
    if not media:
        return None, None
    file_name = get_file_name(message, media, media_type)
    dest_dir = get_media_path(media_type)
    dest_path = os.path.join(dest_dir, file_name)
    if skip_existing and os.path.exists(dest_path):
        md5 = compute_md5(dest_path)
        if md5 and dest_path in existing_media and existing_media[dest_path] == md5:
            return dest_path, md5
        if md5:
            return dest_path, md5
    try:
        async with semaphore:
            downloaded = await client.download_media(message, file=dest_path)
        if downloaded:
            md5 = compute_md5(downloaded) if isinstance(downloaded, str) else None
            return str(downloaded) if downloaded else dest_path, md5
        return dest_path, None
    except Exception as e:
        log.error(f"Failed to download media for msg {message.id}: {e}")
        return None, None

def save_message(msg):
    sender = msg.sender
    sender_name = None
    sender_id = None
    if sender:
        sender_name = getattr(sender, "username", None) or getattr(sender, "first_name", None)
        sender_id = sender.id
    media = msg.media
    media_type = None
    media_path = None
    file_name = None
    file_size = None
    mime_type = None
    md5_hash = None
    if media and not isinstance(media, MessageMediaWebPage):
        cat, _ = get_media_category(media)
        media_type = cat
        if cat:
            file_name = get_file_name(msg, media, cat)
            dest_dir = get_media_path(cat)
            media_path = os.path.join(dest_dir, file_name)
            if hasattr(media, "document") and media.document:
                file_size = media.document.size
                mime_type = media.document.mime_type
            elif hasattr(media, "photo"):
                file_size = getattr(media.photo, "sizes", [None]) and None
    views = getattr(msg, "views", None)
    if views is None:
        views = getattr(msg, "forwards", None)
    text = msg.text or msg.message or ""
    return {
        "id": msg.id,
        "date": msg.date.isoformat() if msg.date else None,
        "text": text,
        "sender_id": sender_id,
        "sender_name": sender_name,
        "message_type": type(msg).__name__,
        "views": views,
        "media_path": media_path,
        "media_type": media_type,
        "file_name": file_name,
        "file_size": file_size,
        "mime_type": mime_type,
        "md5_hash": md5_hash,
    }

def export_json(messages):
    path = os.path.join(OUTPUT_DIR, "messages.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(messages, f, ensure_ascii=False, indent=2)
    log.info(f"JSON exported: {path} ({len(messages)} messages)")

def export_csv(messages):
    path = os.path.join(OUTPUT_DIR, "messages.csv")
    if not messages:
        log.warning("No messages to export to CSV")
        return
    fields = list(messages[0].keys())
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(messages)
    log.info(f"CSV exported: {path} ({len(messages)} messages)")

def export_sqlite(all_data):
    conn = db.init_sync()
    for data in all_data:
        db.insert_message(conn, data)
    db.close(conn)
    log.info(f"SQLite exported: {db.DB_PATH} ({len(all_data)} messages)")

def resume_backup(db_conn):
    last_id = db.get_last_id(db_conn)
    existing_media = db.get_media_map(db_conn)
    return last_id, existing_media

def parse_args():
    parser = argparse.ArgumentParser(description="Backup a Telegram channel completely.")
    parser.add_argument("--only-media", action="store_true", help="Download only media files")
    parser.add_argument("--only-text", action="store_true", help="Save only text messages")
    parser.add_argument("--start-date", type=str, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end-date", type=str, help="End date (YYYY-MM-DD)")
    parser.add_argument("--media-type", type=str, choices=list(MEDIA_DIRS.keys()) + ["all"], default="all", help="Filter by media type")
    parser.add_argument("--skip-existing", action="store_true", help="Skip already downloaded files")
    parser.add_argument("--no-sqlite", action="store_true", help="Skip SQLite export")
    parser.add_argument("--resume", action="store_true", default=True, help="Resume from last checkpoint (default: True)")
    parser.add_argument("--no-resume", action="store_false", dest="resume", help="Start fresh backup")
    return parser.parse_args()

async def main():
    global semaphore, start_time
    start_time = datetime.now()
    validate()
    args = parse_args()
    create_folders()
    await login()
    semaphore = asyncio.Semaphore(CONCURRENT_DOWNLOADS)

    db_conn = db.init_sync()
    offset_id = 0
    existing_media = {}
    if args.resume:
        last_id, existing_media = resume_backup(db_conn)
        if last_id:
            offset_id = last_id
            log.info(f"Resuming from message ID {last_id} (offset_id={offset_id})")

    channel = await client.get_entity(CHANNEL)
    total = await client.get_messages(channel, limit=1)
    total_count = total.total if hasattr(total, 'total') and total.total else None
    if total_count is None:
        try:
            total_count = (await client.get_messages(channel, limit=0)).total
        except Exception:
            total_count = None
    log.info(f"Backing up channel: {CHANNEL} (~{total_count or 'unknown'} messages)")
    all_messages = []

    date_filter = None
    if args.start_date:
        from datetime import timedelta
        date_filter = datetime.strptime(args.start_date, "%Y-%m-%d")
    end_date_filter = None
    if args.end_date:
        end_date_filter = datetime.strptime(args.end_date, "%Y-%m-%d") + timedelta(days=1)

    msg_iter = client.iter_messages(channel, offset_id=offset_id, reverse=True)
    pbar = tqdm(desc="Processing messages", unit=" msg", total=total_count)
    async for msg in msg_iter:
        try:
            if date_filter and msg.date and msg.date.replace(tzinfo=None) < date_filter:
                pbar.update(1)
                continue
            if end_date_filter and msg.date and msg.date.replace(tzinfo=None) > end_date_filter:
                pbar.update(1)
                continue

            data = save_message(msg)

            if args.only_text and msg.media:
                if data["text"]:
                    all_messages.append(data)
                    db.insert_message(db_conn, data)
                pbar.update(1)
                continue

            if args.only_media and not msg.media:
                pbar.update(1)
                continue

            media = msg.media
            if media and not isinstance(media, MessageMediaWebPage):
                cat, _ = get_media_category(media)
                if cat and (args.media_type == "all" or args.media_type == cat):
                    media_path, md5_hash = await download_media(
                        msg, media, cat, args.skip_existing, existing_media
                    )
                    data["media_path"] = media_path
                    data["md5_hash"] = md5_hash

            if args.only_media and not data.get("media_path"):
                pbar.update(1)
                continue

            all_messages.append(data)
            db.insert_message(db_conn, data)

            if msg.id % 100 == 0:
                processed = len(all_messages)
                log.info(f"Progress: id={msg.id} | saved={processed}")

            pbar.update(1)

        except FloodWaitError as e:
            wait = e.seconds
            log.warning(f"FloodWait: waiting {wait}s ({wait/60:.1f}min)")
            pbar.set_description(f"FloodWait {wait}s")
            for remaining in tqdm(range(wait), desc="Waiting", unit="s"):
                await asyncio.sleep(1)
            pbar.set_description("Processing messages")
            if data:
                all_messages.append(data)
                db.insert_message(db_conn, data)
                pbar.update(1)

        except Exception as e:
            log.error(f"Error processing msg {msg.id}: {e}")
            continue

    pbar.close()
    db.close(db_conn)

    elapsed = datetime.now() - start_time
    log.info(f"Processed {len(all_messages)} messages in {elapsed}")
    export_json(all_messages)
    export_csv(all_messages)
    log.info("Backup completed successfully!")

if __name__ == "__main__":
    asyncio.run(main())
