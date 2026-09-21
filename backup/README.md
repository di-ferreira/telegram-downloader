# Telegram Channel Backup

Ferramenta para backup completo de canais do Telegram usando Telethon.

## Requisitos

- Python 3.12+
- Credenciais de API do Telegram ([my.telegram.org/apps](https://my.telegram.org/apps))

## Instalação

```bash
pip install -r requirements.txt
```

## Configuração

Copie o arquivo de exemplo e edite com seus dados:

```bash
cp .env.example .env
```

### Variáveis do `.env`

| Variável | Obrigatório | Descrição |
|---|---|---|
| `API_ID` | Sim | Seu API ID (my.telegram.org) |
| `API_HASH` | Sim | Seu API Hash (my.telegram.org) |
| `CHANNEL` | Sim | Username do canal (`@canal`), ID numérico (`-100XXXXX`) ou link de convite |
| `OUTPUT_DIR` | Não | Pasta de saída (padrão: `downloads`) |
| `CONCURRENT_DOWNLOADS` | Não | Downloads simultâneos (padrão: `5`) |
| `SESSION_NAME` | Não | Nome do arquivo de sessão (padrão: `telegram_backup`) |

> Na primeira execução o Telegram solicitará seu número de telefone e código de verificação.

## Como usar

Execute a partir da raiz do projeto:

```bash
python backup/backup.py
```

Ou diretamente da pasta `backup/`:

```bash
cd backup
python backup.py
```

O script baixará todas as mensagens e mídias do canal, salvando na pasta definida em `OUTPUT_DIR`.

## Opções

| Argumento | Descrição |
|---|---|
| `--only-media` | Baixa apenas arquivos de mídia (ignora mensagens de texto) |
| `--only-text` | Salva apenas mensagens de texto (ignora mídias) |
| `--start-date YYYY-MM-DD` | Filtra mensagens a partir desta data |
| `--end-date YYYY-MM-DD` | Filtra mensagens até esta data |
| `--media-type {photo,video,document,audio,gif,sticker,all}` | Filtra por tipo de mídia |
| `--skip-existing` | Pula arquivos já baixados (usando hash MD5) |
| `--no-sqlite` | Não cria banco SQLite |
| `--no-resume` | Ignora checkpoint anterior e recomeça do zero |
| `--message-id ID [ID ...]` | Baixa mensagem(s) específica(s) pelo ID |
| `--list-channels` | Lista todos os canais e grupos acessíveis |
| `-S`, `--save` | Salva a saída do `--list-channels` em `channels.txt` |

## Exemplos

### Backup completo

```bash
python backup/backup.py
```

### Apenas fotos e vídeos de 2024

```bash
python backup/backup.py \
    --only-media \
    --start-date 2024-01-01 \
    --end-date 2024-12-31
```

### Apenas documentos PDF

```bash
python backup/backup.py --only-media --media-type document
```

### Apenas textos

```bash
python backup/backup.py --only-text
```

### Evitar redownload

```bash
python backup/backup.py --skip-existing
```

### Recomeçar do zero (ignorar progresso anterior)

```bash
python backup/backup.py --no-resume
```

### Baixar um post específico

```bash
python backup/backup.py --message-id 3
```

### Baixar múltiplos posts

```bash
python backup/backup.py --message-id 3 7 15 42
```

### Baixar post específico filtrando tipo de mídia

```bash
python backup/backup.py --message-id 3 --media-type video
```

### Listar canais acessíveis

```bash
python backup/backup.py --list-channels
```

### Listar canais e salvar em arquivo

```bash
python backup/backup.py --list-channels --save
# ou
python backup/backup.py --list-channels -S
```

> O arquivo `channels.txt` é criado na pasta `backup/` com o ID, tipo, username e título de cada canal.

## Retomada automática

O script salva o progresso no banco SQLite (`backup.db`). Se for interrompido (Ctrl+C, queda de conexão, etc.), basta executar novamente que ele continuará de onde parou.

Para forçar o início do zero, use `--no-resume`.

## Estrutura de saída

```
downloads/
├── media/
│   ├── photos/          # Fotos e imagens
│   ├── videos/          # Vídeos
│   ├── documents/       # PDFs, arquivos compactados, etc.
│   ├── audios/          # Áudios e músicas
│   ├── gifs/            # GIFs
│   ├── stickers/        # Stickers
│   └── others/          # Outros tipos de mídia
├── messages.json        # Metadados das mensagens (JSON)
├── messages.csv         # Metadados das mensagens (CSV)
├── backup.db            # Banco SQLite com metadados
└── log.txt              # Log detalhado da execução
```

## Funcionalidades

- Backup completo de mensagens e todos os tipos de mídia
- Download de posts específicos por ID (`--message-id`)
- Listagem de canais acessíveis (`--list-channels`)
- Suporte a canais privados por ID numérico
- Retomada automática de execuções interrompidas
- Tratamento de FloodWait com espera automática
- Downloads simultâneos (configurável)
- Exportação em JSON, CSV e SQLite
- Hash MD5 para evitar duplicatas
- Filtros por data e tipo de mídia
- Barra de progresso com tqdm
- Logs detalhados
