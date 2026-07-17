# Telegram Downloader

Ferramentas para backup e restore de canais do Telegram.

## Estrutura

```
├── backup/          # Scripts para backup de canais
├── restore/         # Scripts para restore de backups
└── README.md
```

## Backup

```bash
pip install -r backup/requirements.txt
cp backup/.env.example backup/.env
# editar backup/.env
python backup/backup.py
```

## Restore

```bash
pip install -r restore/requirements.txt
cp restore/.env.example restore/.env
# editar restore/.env
python restore/main.py
```
