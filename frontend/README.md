# Frontend — Telegram Downloader

Interface local (Streamlit) para navegar no conteúdo baixado pelo `backup/`,
acompanhar o progresso de vídeos assistidos e disparar backups/restores com log ao vivo.

A spec completa está em [`SPEC.md`](SPEC.md).

## Requisitos

- Python 3.11+ (o mesmo interpretador do restante do projeto)
- Um backup gerado (`python backup/backup.py`) com `backup.db` / `messages.json` e `media/`

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
| `core/stats.py` | métricas, gráficos, tamanhos de pasta |
| `core/exports.py` | CSV/JSON/ZIP das mensagens filtradas |
| `components/` | player JS, filtros, cards da galeria, helpers de UI |
| `pages/` | Dashboard, Mensagens, Galeria, Reprodutor, Fontes, Backup & Restore |

## Páginas

- **Dashboard** — métricas, gráficos, "continuar assistindo", estrutura e execuções.
- **Mensagens** — filtros + tabela + detalhe, favoritos, anotações, export CSV/JSON/ZIP.
- **Galeria** — grade de mídia com miniaturas, abrindo direto no reprodutor.
- **Reprodutor** — fila, retoma do último ponto, progresso salvo (≥95% = assistido).
- **Fontes** — adicionar/procurar/escanear/re-escanear pastas de backup.
- **Backup & Restore** — formulários com opções do CLI, log ao vivo e cancelamento.

## Segurança

- O banco de conteúdo é aberto **somente leitura** (`file:...?mode=ro`).
- O servidor de mídia escuta apenas em `127.0.0.1`.
- O Streamlit também é forçado a `127.0.0.1` pelo `.streamlit/config.toml` da
  raiz do repositório — sem ele, o Streamlit escuta em `0.0.0.0` e exporia a
  interface na rede.
- Credenciais do `.env` nunca são exibidas (apenas mascaradas).

## Variáveis (opcionais)

| Variável | Padrão |
| --- | --- |
| `FRONTEND_LIBRARY_DB` | `frontend/library.db` |
| `FRONTEND_LOG_DIR` | `frontend/logs` |
| `FRONTEND_MEDIA_PORT` | `0` (porta livre) |
| `FRONTEND_PAGE_SIZE` | `50` |
| `FRONTEND_WATCHED_AT` | `0.95` |
| `FRONTEND_AUTO_SCAN` | `true` |
