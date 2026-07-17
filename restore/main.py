#!/usr/bin/env python3
import asyncio
import argparse
import sys
import os

from config import validate, BACKUP_FOLDER
from restore import run_restore


def parse_args():
    parser = argparse.ArgumentParser(
        description="Restore a Telegram channel from a backup."
    )

    parser.add_argument(
        "--backup-folder",
        type=str,
        default=BACKUP_FOLDER,
        help=f"Path to backup folder (default: {BACKUP_FOLDER})",
    )

    parser.add_argument(
        "--start-date",
        type=str,
        help="Restore only messages from this date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--end-date",
        type=str,
        help="Restore only messages until this date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--start-id",
        type=int,
        help="Restore only messages with ID >= this value",
    )
    parser.add_argument(
        "--end-id",
        type=int,
        help="Restore only messages with ID <= this value",
    )

    parser.add_argument(
        "--only-media",
        action="store_true",
        help="Restore only messages that have media",
    )
    parser.add_argument(
        "--only-text",
        action="store_true",
        help="Restore only text messages (no media)",
    )
    parser.add_argument(
        "--media-type",
        type=str,
        choices=["photo", "video", "document", "audio", "gif", "sticker", "all"],
        default="all",
        help="Filter by media type (default: all)",
    )

    parser.add_argument(
        "--retry-errors",
        action="store_true",
        help="Retry only previously failed messages",
    )
    parser.add_argument(
        "--channel-id",
        type=str,
        help="Channel ID/username for retry (required with --retry-errors)",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate restore without publishing anything",
    )

    return parser.parse_args()


def main():
    validate()
    args = parse_args()

    if args.retry_errors and not args.channel_id:
        print("ERROR: --channel-id is required when using --retry-errors")
        sys.exit(1)
    if args.only_media and args.only_text:
        print("ERROR: --only-media and --only-text are mutually exclusive")
        sys.exit(1)

    os.makedirs("logs", exist_ok=True)

    asyncio.run(run_restore(args))


if __name__ == "__main__":
    main()
