# Telegram Channel Backup

Complete backup tool for Telegram channels using Telethon.

## Requirements

- Python 3.12+
- Telegram API credentials ([my.telegram.org/apps](https://my.telegram.org/apps))

## Setup

1. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

2. Copy `.env.example` to `.env`:

   ```bash
   cp .env.example .env
   ```

3. Edit `.env` with your credentials.

### How to get API_ID and API_HASH

1. Go to https://my.telegram.org/apps
2. Log in with your Telegram account
3. Create a new application
4. Copy the `api_id` and `api_hash` values

## Usage

Run from the project root:

```bash
python backup/backup.py
```

### Options

| Argument | Description |
|---|---|
| `--only-media` | Download only media files |
| `--only-text` | Save only text messages |
| `--start-date YYYY-MM-DD` | Start date filter |
| `--end-date YYYY-MM-DD` | End date filter |
| `--media-type {photo,video,document,audio,gif,sticker,all}` | Filter by media type |
| `--skip-existing` | Skip already downloaded files (uses MD5) |
| `--no-sqlite` | Skip SQLite database creation |
| `--no-resume` | Start a fresh backup (ignore checkpoint) |

### Examples

```bash
# Full backup
python backup/backup.py

# Only photos and videos
python backup/backup.py --only-media --media-type photo
python backup/backup.py --only-media --media-type video

# Specific date range
python backup/backup.py --start-date 2024-01-01 --end-date 2024-12-31

# Skip already downloaded files
python backup/backup.py --skip-existing

# Fresh backup (ignore previous progress)
python backup/backup.py --no-resume
```

## Output Structure

```
downloads/
├── media/
│   ├── photos/
│   ├── videos/
│   ├── documents/
│   ├── audios/
│   ├── gifs/
│   ├── stickers/
│   └── others/
├── messages.json
├── messages.csv
├── backup.db
└── log.txt
```

## Features

- Full channel backup (messages + all media types)
- Resume support from last checkpoint
- FloodWait handling with automatic retry
- Configurable concurrent downloads
- Export to JSON, CSV, and SQLite
- MD5 hash deduplication
- Date range and media type filters
- Progress bar with tqdm
- Detailed logging
