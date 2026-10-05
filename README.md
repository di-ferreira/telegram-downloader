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
cd backup
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# editar .env
python backup.py
```

> O venv precisa estar ativado antes de rodar o script, senão o `python` do sistema não terá o Telethon.

## Restore

```bash
pip install -r restore/requirements.txt
cp restore/.env.example restore/.env
# editar restore/.env
python restore/main.py
```
