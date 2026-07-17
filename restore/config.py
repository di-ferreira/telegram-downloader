import os
from pathlib import Path
from dotenv import load_dotenv

env_path = Path.cwd() / ".env"
if not env_path.exists():
    env_path = Path(__file__).parent / ".env"
load_dotenv(env_path)

API_ID = int(os.getenv("API_ID", 0))
API_HASH = os.getenv("API_HASH", "")
PHONE = os.getenv("PHONE", "")

CHANNEL_NAME = os.getenv("CHANNEL_NAME", "Restored Channel")
CHANNEL_DESCRIPTION = os.getenv("CHANNEL_DESCRIPTION", "")
CHANNEL_USERNAME = os.getenv("CHANNEL_USERNAME", "")

BACKUP_FOLDER = os.getenv("BACKUP_FOLDER", "downloads")

SESSION_NAME = os.getenv("SESSION_NAME", "telegram_restore")


def validate():
    errors = []
    if not API_ID:
        errors.append("API_ID is required")
    if not API_HASH:
        errors.append("API_HASH is required")
    if not PHONE:
        errors.append("PHONE is required")
    if not CHANNEL_NAME:
        errors.append("CHANNEL_NAME is required")
    if errors:
        raise ValueError("Missing config:\n" + "\n".join(errors))
    return True
