# Frontend — Telegram Downloader

Interface local (Streamlit) para navegar no conteúdo baixado pelo `backup/`,
acompanhar o progresso de vídeos assistidos e disparar backups/restores com log ao vivo.

A spec completa está em [`SPEC.md`](SPEC.md); configuração e operação do
`backup/`/`restore/` estão em [`SPEC-BACKEND.md`](SPEC-BACKEND.md).

## Requisitos

- Python 3.11+ (o mesmo interpretador do restante do projeto)
- Um backup gerado (`python backup/backup.py`) com `backup.db` / `messages.json` e `media/`
- Para disparar jobs: `.env` na raiz, `telethon`/`tqdm`/`python-dotenv` instalados
  e uma sessão `.session` criada (uma vez, via CLI)

## Instalação

```powershell
pip install -r frontend/requirements.txt
```

## Execução

```powershell
streamlit run frontend/streamlit_app.py
```

O servidor sobe em `http://localhost:8501` (apenas local).

## O que existe em `frontend/`

| Arquivo | Papel |
| --- | --- |
| `streamlit_app.py` | entrada: sidebar, fonte ativa, navegação |
| `config.py` | caminhos, portas e limites |
| `core/registry.py` | `library.db` — fontes, progresso, favoritos, jobs, FTS |
| `core/queries.py` | busca (FTS5 + fallback LIKE/JSON), paginação, exports |
| `core/content.py` | detecção/scan da pasta de backup, FTS de texto |
| `core/media_server.py` | servidor HTTP em `127.0.0.1` com suporte a Range |
| `core/job_runner.py` | spawna `backup.py` / `restore/main.py`, log por job |
| `core/envfile.py` | `.env` da raiz: ler, mascarar, merge atômico + `.env.bak` |
| `core/preflight.py` | checagens pré-job (`.env`, dependências, sessão, pasta) |
| `core/backend_state.py` | leitura dos artefatos/progresso/logs do backend |
| `core/channels.py` | canais do `--list-channels`: busca/filtro, pasta por canal, download, fonte, tamanho |
| `core/telestat.py` | estimativa de tamanho de canais (Telethon, amostra) + cache |
| `core/sessions.py` | qual `.session` está autorizada (raiz/backup/restore) + `SESSION_NAME` dos jobs |
| `core/stats.py` | métricas, gráficos, tamanhos de pasta |
| `core/exports.py` | CSV/JSON/ZIP das mensagens filtradas |
| `login.py` | CLI de 1º acesso: cria a sessão `.session` do Telethon |
| `components/` | player JS, filtros, cards da galeria, helpers de UI |
| `pages/` | Dashboard, Mensagens, Galeria, Reprodutor, Fontes, Backup & Restore, Backends, Configurações |

## Páginas

- **Dashboard** — métricas, gráficos, "continuar assistindo", estrutura e execuções.
- **Mensagens** — filtros + tabela + detalhe, favoritos, anotações, export CSV/JSON/ZIP.
- **Galeria** — grade de mídia com miniaturas, abrindo direto no reprodutor.
- **Reprodutor** — fila, retoma do último ponto, progresso salvo (≥95% = assistido).
- **Fontes** — adicionar/procurar/escanear/re-escanear pastas de backup.
- **Backup & Restore** — formulários com opções do CLI, log ao vivo e cancelamento.
- **Backends** — canais acessíveis com **busca** (filtra por título, @username ou
  ID, com paginação), **coluna Tamanho** (exato em disco para canais baixados;
  📏 estimativa `≈` sob demanda via Telegram, cacheada em
  `frontend/.cache/channel_sizes.json`) e **coluna Download** (⬇️ baixa o canal —
  grava `CHANNEL`/`OUTPUT_DIR` no `.env` e salva em `OUTPUT_BASE/<título>` — ou
  abre 🖼️ Galeria / ▶️ Reprodutor quando já baixado), saídas do backup,
  simulação (dry-run), progresso real do restore e logs.
- **Configurações** — status de `.env`/dependências/sessão e os forms para
  preencher as credenciais.

## Configuração do backend

As duas ferramentas leem `Path.cwd()/".env"` e os jobs rodam com cwd na raiz do
repositório, então existe **um único `.env` na raiz**, editável na página
*Configurações* (criação, merge preservando comentários, backup `.env.bak`).

```powershell
pip install -r backup/requirements.txt -r restore/requirements.txt
streamlit run frontend/streamlit_app.py       # Configurações -> preencher .env
python frontend/login.py                      # 1º acesso: telefone + código
```

Sem `.env`, sem dependências ou sem sessão, os botões de disparo ficam
desabilitados com o comando exato de correção (ver SPEC-BACKEND §3).

## Segurança

- O banco de conteúdo é aberto **somente leitura** (`file:...?mode=ro`).
- O servidor de mídia escuta apenas em `127.0.0.1`.
- O Streamlit também é forçado a `127.0.0.1` pelo `.streamlit/config.toml` da
  raiz do repositório — sem ele, o Streamlit escuta em `0.0.0.0` e exporia a
  interface na rede.
- Credenciais do `.env` nunca são exibidas (apenas mascaradas) e o arquivo fica
  fora do git (`.env`, `.env.bak`, `.env.tmp` no `.gitignore`); gravações são
  atômicas e preservam o arquivo anterior.

## Variáveis (opcionais)

| Variável | Padrão |
| --- | --- |
| `FRONTEND_LIBRARY_DB` | `frontend/library.db` |
| `FRONTEND_LOG_DIR` | `frontend/logs` |
| `FRONTEND_MEDIA_PORT` | `0` (porta livre) |
| `FRONTEND_PAGE_SIZE` | `50` |
| `FRONTEND_WATCHED_AT` | `0.95` |
| `FRONTEND_AUTO_SCAN` | `true` |
