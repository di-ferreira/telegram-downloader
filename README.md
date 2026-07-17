# Telegram Downloader

Ferramentas para backup e restore de canais do Telegram.

## Estrutura

```
├── backup/          # Scripts para backup de canais
├── restore/         # Scripts para restore de backups
├── Prompt_backup.md    # Especificação do backup
├── Prompt_restore.md   # Especificação do restore
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

*(em desenvolvimento)*
