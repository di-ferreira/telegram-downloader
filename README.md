# Telegram Channel Backup

Complete backup tool for Telegram channels using Telethon.

## Requirements

- Python 3.12+
- Telegram API credentials ([my.telegram.org/apps](https://my.telegram.org/apps))

## Setup

1. Clone or download the script files.

2. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

3. Copy `.env.example` to `.env` and fill in your credentials:

   ```bash
   cp .env.example .env
   ```

4. Edit `.env`:

   - `API_ID` – Your API ID from [my.telegram.org](https://my.telegram.org/apps)
   - `API_HASH` – Your API Hash from [my.telegram.org](https://my.telegram.org/apps)
   - `CHANNEL` – Channel username (`@channel`) or invite link
   - `OUTPUT_DIR` – Backup output directory (default: `backup`)
   - `CONCURRENT_DOWNLOADS` – Max simultaneous downloads (default: `5`)

## How to get API_ID and API_HASH

1. Go to https://my.telegram.org/apps
2. Log in with your Telegram account
3. Create a new application if none exists
4. Copy the `api_id` and `api_hash` values

## Usage

```bash
python backup.py
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
python backup.py

# Only photos and videos
python backup.py --only-media --media-type photo
python backup.py --only-media --media-type video

# Specific date range
python backup.py --start-date 2024-01-01 --end-date 2024-12-31

# Skip already downloaded files
python backup.py --skip-existing

# Fresh backup (ignore previous progress)
python backup.py --no-resume
```

## Output Structure

```
backup/
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
- Resume support – continues from where it stopped
- FloodWait handling with automatic retry
- Configurable concurrent downloads
- Export to JSON, CSV, and SQLite
- MD5 hash deduplication
- Date range and media type filters
- Progress bar with tqdm
- Detailed logging
