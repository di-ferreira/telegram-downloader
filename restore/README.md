# Telegram Channel Restore

Restaura um canal do Telegram a partir de um backup completo (criado pelo script `backup/`).

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
| `PHONE` | Sim | Telefone com código do país (`+5511999999999`) |
| `CHANNEL_NAME` | Sim | Nome do novo canal |
| `CHANNEL_DESCRIPTION` | Não | Descrição do novo canal |
| `CHANNEL_USERNAME` | Não | Username desejado (ex: `meu_canal`) |
| `BACKUP_FOLDER` | Não | Pasta do backup (padrão: `downloads`) |
| `SESSION_NAME` | Não | Nome da sessão (padrão: `telegram_restore`) |

## Como usar

Execute da raiz do projeto:

```bash
python restore/main.py
```

## Opções

| Argumento | Descrição |
|---|---|
| `--backup-folder PATH` | Caminho da pasta de backup |
| `--start-date YYYY-MM-DD` | Restaura apenas a partir desta data |
| `--end-date YYYY-MM-DD` | Restaura apenas até esta data |
| `--start-id ID` | Restaura mensagens com ID >= valor |
| `--end-id ID` | Restaura mensagens com ID <= valor |
| `--only-media` | Restaura apenas mensagens com mídia |
| `--only-text` | Restaura apenas mensagens de texto |
| `--media-type {photo,video,document,audio,gif,sticker,all}` | Filtra por tipo de mídia |
| `--retry-errors` | Tenta novamente mensagens que falharam |
| `--channel-id ID` | ID/username do canal (usado com `--retry-errors`) |
| `--dry-run` | Simulação: mostra estatísticas sem publicar |

## Exemplos

### Restauração completa

```bash
cp .env.example .env
# editar .env com suas credenciais
python restore/main.py
```

### Restaurar apenas um intervalo de datas

```bash
python restore/main.py --start-date 2024-01-01 --end-date 2024-06-30
```

### Apenas fotos e vídeos

```bash
python restore/main.py --only-media
```

### Apenas documentos

```bash
python restore/main.py --media-type document
```

### Simular antes de restaurar

```bash
python restore/main.py --dry-run
```

### Re-tentar mensagens com erro

```bash
python restore/main.py --retry-errors --channel-id -1001234567890
```

## Fluxo de execução

1. Lê o backup (`backup.db` ou `messages.json`)
2. Cria um novo canal no Telegram
3. Publica mensagens em ordem cronológica original
4. Envia mídias associadas
5. Aplica intervalos de segurança entre mensagens
6. Salva progresso a cada mensagem

## Retomada automática

O script salva o progresso em `restore_progress.db`. Se for interrompido, execute novamente que ele continuará de onde parou.

Estrutura de saída dos logs:
```
logs/
├── restore.log        # Log completo da execução
├── errors.log         # Apenas erros
└── missing_media.log  # Arquivos de mídia ausentes
```
