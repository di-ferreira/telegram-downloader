import os
from pathlib import Path
from dotenv import load_dotenv

env_path = Path.cwd() / ".env"
if not env_path.exists():
    env_path = Path(__file__).parent / ".env"
load_dotenv(env_path)

API_ID = int(os.getenv("API_ID", 0))
API_HASH = os.getenv("API_HASH", "")
CHANNEL = os.getenv("CHANNEL", "")
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "downloads")
CONCURRENT_DOWNLOADS = int(os.getenv("CONCURRENT_DOWNLOADS", 5))
SESSION_NAME = os.getenv("SESSION_NAME", "telegram_backup")

def validate():
    errors = []
    if not API_ID:
        errors.append("API_ID is required")
    if not API_HASH:
        errors.append("API_HASH is required")
    if not CHANNEL:
        errors.append("CHANNEL is required")
    if errors:
        raise ValueError("Missing config:\n" + "\n".join(errors))
    return True
