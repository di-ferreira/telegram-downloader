import os
import asyncio
import random
import time
import logging
from datetime import datetime

from telethon import TelegramClient
from telethon.errors import FloodWaitError, ChannelInvalidError
from telethon.tl.functions.channels import CreateChannelRequest, EditTitleRequest, EditAboutRequest
from telethon.tl.functions.account import UpdateUsernameRequest

from config import API_ID, API_HASH, PHONE, SESSION_NAME
from config import CHANNEL_NAME, CHANNEL_DESCRIPTION, CHANNEL_USERNAME
import database as db
import logger as lmod

log = logging.getLogger(__name__)
client = None
channel = None
progress_conn = None

INTERVALO_BASE = (2, 5)
INTERVALO_LONGO = (30, 60)
MENSAGENS_PARA_INTERVALO_LONGO = 20


async def login():
    global client
    client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
    await client.start(phone=PHONE)
    me = await client.get_me()
    log.info(f"Logged in as {me.username or me.first_name} (ID: {me.id})")
    return client


async def create_channel():
    global channel
    log.info(f"Creating channel '{CHANNEL_NAME}'...")
    try:
        result = await client(CreateChannelRequest(
            title=CHANNEL_NAME,
            about=CHANNEL_DESCRIPTION,
            megagroup=False,
        ))
        channel = result.chats[0]
        log.info(f"Channel created: {channel.title} (ID: {channel.id})")
        if CHANNEL_USERNAME:
            try:
                await client(UpdateUsernameRequest(channel.id, CHANNEL_USERNAME))
                log.info(f"Username set to @{CHANNEL_USERNAME}")
            except Exception as e:
                log.warning(f"Could not set username: {e}")
        return channel
    except Exception as e:
        log.error(f"Failed to create channel: {e}")
        raise


async def send_text(message_data):
    text = message_data.get("text") or ""
    if not text:
        return None
    return await client.send_message(channel, text, parse_mode="html")


async def send_media(message_data):
    media_path = message_data.get("media_path")
    if not media_path or not os.path.exists(media_path):
        log.warning(f"Media file not found: {media_path}")
        return None

    file_path = media_path
    caption = message_data.get("text") or ""
    mime = message_data.get("mime_type") or ""
    media_type = message_data.get("media_type") or ""

    try:
        if media_type == "sticker":
            return await client.send_file(channel, file_path)
        elif media_type == "photo" or mime.startswith("image/"):
            return await client.send_file(channel, file_path, caption=caption)
        elif media_type == "gif" or mime == "image/gif":
            return await client.send_file(channel, file_path, caption=caption, supports_streaming=True)
        elif media_type == "video" or mime.startswith("video/"):
            return await client.send_file(channel, file_path, caption=caption, supports_streaming=True)
        elif media_type == "audio" or mime.startswith("audio/"):
            return await client.send_file(channel, file_path, caption=caption)
        else:
            return await client.send_file(channel, file_path, caption=caption)
    except Exception as e:
        log.error(f"Failed to send media {file_path}: {e}")
        return None


async def restore_message(message_data, dry_run=False):
    msg_id = message_data.get("id")
    media_path = message_data.get("media_path")
    text = message_data.get("text") or ""

    if dry_run:
        has_media = media_path and os.path.exists(media_path)
        return {
            "id": msg_id,
            "text": bool(text),
            "media": has_media,
            "media_path": media_path if has_media else None,
        }

    result = None
    if media_path and os.path.exists(media_path):
        result = await send_media(message_data)
    elif text.strip():
        result = await send_text(message_data)

    return result


async def run_restore(args):
    global progress_conn, channel

    lmod.create_logs()
    log = logging.getLogger(__name__)
    progress_conn = db.init_progress()

    log.info("Loading backup...")
    all_messages = db.load_messages(args.backup_folder)
    log.info(f"Loaded {len(all_messages)} messages from backup")

    if args.start_id:
        all_messages = [m for m in all_messages if m["id"] >= args.start_id]
    if args.end_id:
        all_messages = [m for m in all_messages if m["id"] <= args.end_id]
    if args.start_date:
        all_messages = [m for m in all_messages if m.get("date", "")[:10] >= args.start_date]
    if args.end_date:
        all_messages = [m for m in all_messages if m.get("date", "")[:10] <= args.end_date]
    if args.media_type and args.media_type != "all":
        all_messages = [m for m in all_messages if m.get("media_type") == args.media_type]
    if args.only_media:
        all_messages = [m for m in all_messages if m.get("media_path")]
    if args.only_text:
        all_messages = [m for m in all_messages if not m.get("media_path")]

    if args.dry_run:
        total_media = sum(1 for m in all_messages if m.get("media_path") and os.path.exists(m["media_path"]))
        total_size = sum(
            os.path.getsize(m["media_path"]) for m in all_messages
            if m.get("media_path") and os.path.exists(m["media_path"])
        )
        missing_media = [
            m["media_path"] for m in all_messages
            if m.get("media_path") and not os.path.exists(m["media_path"])
        ]
        print(f"\n{'='*50}")
        print(f"DRY RUN — {CHANNEL_NAME}")
        print(f"{'='*50}")
        print(f"Total messages:       {len(all_messages)}")
        print(f"With media:           {total_media}")
        print(f"Text only:            {len(all_messages) - total_media}")
        print(f"Total media size:     {total_size / 1024 / 1024:.2f} MB")
        print(f"Missing media files:  {len(missing_media)}")
        if missing_media:
            print(f"\nMissing files:")
            for p in missing_media[:10]:
                print(f"  - {p}")
            if len(missing_media) > 10:
                print(f"  ... and {len(missing_media) - 10} more")
        return

    await login()

    if args.retry_errors:
        pending = db.get_pending(progress_conn)
        all_messages = [m for m in all_messages if m["id"] in pending]
        log.info(f"Retrying {len(all_messages)} failed messages")
        if not all_messages:
            log.info("No errors to retry")
            return
        channel_entity = await client.get_entity(int(args.channel_id))
        channel = channel_entity
    else:
        channel = await create_channel()

    last_sent, progress = db.resume_restore(progress_conn)
    if last_sent is not None and not args.retry_errors:
        resume_index = None
        for i, m in enumerate(all_messages):
            if m["id"] > last_sent:
                resume_index = i
                break
        if resume_index is not None:
            all_messages = all_messages[resume_index:]
            log.info(f"Resuming from message ID {last_sent + 1} ({len(all_messages)} remaining)")
        else:
            log.info("All messages already restored")

    from tqdm import tqdm
    pbar = tqdm(all_messages, desc="Restoring", unit=" msg")

    sent_count = 0
    for msg_data in pbar:
        msg_id = msg_data["id"]
        status = progress.get(msg_id)

        if status == "sent" and not args.retry_errors:
            pbar.update(1)
            continue

        max_retries = 3
        restored = False
        for attempt in range(max_retries):
            try:
                result = await restore_message(msg_data)

                if result:
                    novo_id = result.id if hasattr(result, "id") else None
                    db.save_progress(
                        progress_conn,
                        msg_id,
                        novo_id=novo_id,
                        data_envio=datetime.now().isoformat(),
                    )
                else:
                    db.save_progress(
                        progress_conn,
                        msg_id,
                        status="skipped",
                        data_envio=datetime.now().isoformat(),
                    )

                restored = True
                sent_count += 1
                break

            except FloodWaitError as e:
                wait = e.seconds
                log.warning(f"FloodWait #{attempt+1}: waiting {wait}s ({wait/60:.1f}min)")
                pbar.set_description(f"FloodWait {wait}s")
                for _ in tqdm(range(wait), desc="Waiting", unit="s", leave=False):
                    await asyncio.sleep(1)
                pbar.set_description("Restoring")

            except Exception as e:
                log.error(f"Error restoring msg {msg_id}: {e}")
                db.mark_error(progress_conn, msg_id, str(e))
                break

        if not restored:
            db.mark_error(progress_conn, msg_id, "Max retries exceeded")
            continue

        if sent_count % MENSAGENS_PARA_INTERVALO_LONGO == 0:
            delay = random.uniform(*INTERVALO_LONGO)
            log.info(f"Long pause: {delay:.0f}s after {sent_count} messages")
            await asyncio.sleep(delay)
        else:
            delay = random.uniform(*INTERVALO_BASE)
            await asyncio.sleep(delay)

    pbar.close()
    db.close_progress(progress_conn)
    log.info(f"Restore completed! {sent_count} messages processed.")
