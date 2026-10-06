# SPEC — Frontend Streamlit para o Telegram Downloader

## 0. Decisões

| Tema | Decisão |
|---|---|
| UI | Streamlit ≥ 1.65 com `st.navigation` + `st.Page` |
| Escopo | Leitura/mídia/busca **+** execução de backup/restore com log ao vivo |
| Fonte de dados | Banco-índice `library.db` que registra os caminhos dos bancos de conteúdo |
| Progresso | Servidor HTTP loopback servindo `downloads/` + player próprio (`st.components.v2`) |
| Estrutura | Pasta `frontend/` espelhando `backup/` e `restore/` |
| Segurança | Tudo em `127.0.0.1`; bancos de conteúdo abertos **somente leitura** |

## 1. Insumo existente no repositório

- `backup/backup.py` grava em `OUTPUT_DIR` (padrão `downloads/`):
  `media/{photos,videos,documents,audios,gifs,stickers,others}/`, `messages.json`,
  `messages.csv`, `backup.db`, `log.txt`.
- Schema da tabela `messages`:

  ```
  id, date, text, sender_id, sender_name, message_type, views,
  media_path, media_type, file_name, file_size, mime_type, md5_hash
  ```

- `restore/` lê `backup.db` (fallback `messages.json`) — mesma interface usada aqui.
- `.gitignore` já cobre `*.db` e `.env` → `library.db` fica fora do git.
- `media_path` é gravado relativo ao CWD do backup, com separador do OS.
- Pasta `downloads/` pode não existir na primeira execução.

## 2. Estrutura

```
frontend/
├── SPEC.md
├── streamlit_app.py        # entrypoint: navegação, sidebar global, estado
├── requirements.txt
├── config.py               # env FRONTEND_*
├── pages/
│   ├── home.py             # dashboard / biblioteca
│   ├── sources.py          # gerenciar fontes (bancos de conteúdo)
│   ├── browse.py           # mensagens: busca + filtros + tabela + detalhe
│   ├── gallery.py          # galeria de mídia em grid
│   ├── player.py           # reprodutor com fila e progresso
│   └── jobs.py             # executar backup/restore + log ao vivo
├── core/
│   ├── paths.py            # raiz do repo, resolução/normalização de caminhos
│   ├── registry.py         # library.db (schema, migrações, CRUD)
│   ├── content.py          # abertura read-only de backup.db / messages.json
│   ├── queries.py          # listagem, filtros, paginação, FTS5
│   ├── stats.py            # agregações do dashboard
│   ├── media_server.py     # HTTP loopback com suporte a Range
│   ├── job_runner.py       # subprocess + tail de log + cancelamento
│   └── exports.py          # CSV/JSON/ZIP sob demanda
└── components/
    ├── player.py           # componente v2 (vídeo/áudio) que reporta posição
    ├── cards.py            # card de mensagem / miniatura
    └── filters.py          # barra de filtros reutilizável
```

## 3. Banco-índice `frontend/library.db`

```sql
CREATE TABLE sources (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  root_path TEXT NOT NULL UNIQUE,
  db_path TEXT, json_path TEXT,
  channel TEXT, enabled INTEGER DEFAULT 1,
  added_at TEXT, last_scanned_at TEXT,
  message_count INTEGER DEFAULT 0, media_count INTEGER DEFAULT 0,
  total_bytes INTEGER DEFAULT 0, missing_files INTEGER DEFAULT 0
);

CREATE TABLE media_state (
  source_id INTEGER NOT NULL,
  media_key TEXT NOT NULL,
  message_id INTEGER,
  kind TEXT,
  status TEXT DEFAULT 'new',
  position_sec REAL DEFAULT 0, duration_sec REAL DEFAULT 0,
  percent REAL DEFAULT 0,
  play_count INTEGER DEFAULT 0,
  last_played_at TEXT, updated_at TEXT,
  note TEXT,
  PRIMARY KEY (source_id, media_key)
);

CREATE TABLE favorites (
  source_id INTEGER, message_id INTEGER, note TEXT, created_at TEXT,
  PRIMARY KEY (source_id, message_id)
);

CREATE TABLE jobs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  kind TEXT, source_id INTEGER, args TEXT,
  cmd TEXT, cwd TEXT, env TEXT,
  status TEXT DEFAULT 'queued',
  pid INTEGER, exit_code INTEGER,
  started_at TEXT, finished_at TEXT, log_path TEXT, log_tail TEXT
);

CREATE VIRTUAL TABLE fts_msg USING fts5(
  text, sender_name, tokenize='unicode61 remove_diacritics 2'
);
-- ligação: colunas não-fts source_id, message_id
```

Regras:

- `media_key` é relativo ao `root_path` (convertido no scan) → mover a pasta não quebra o histórico.
- Migrações via `PRAGMA user_version`.
- Nunca escrever nos bancos de conteúdo: `sqlite3.connect(f"file:{path}?mode=ro", uri=True)` com `busy_timeout=5000`.

## 4. `core/media_server.py`

- `ThreadingHTTPServer` em `127.0.0.1:0` (porta efêmera), sob `@st.cache_resource`, registrado em `atexit`.
- Rota: `GET /s/{source_id}/{relpath}` → `root / relpath`.
- Suporte a `Range` (`206`, `Content-Range`, `Accept-Ranges: bytes`) — obrigatório para seek em vídeo.
- `Access-Control-Allow-Origin: *`, `Content-Type` via `mimetypes`, streaming em chunks de 64 KB.
- `Path.resolve()` + `is_relative_to(root)` para bloquear path traversal; `urllib.parse.quote` nas URLs.

## 5. `components/player.py` — progresso real

```python
player = st.components.v2.component("media_player", html=..., css=..., js=...)
result = player(data={"src": url, "kind": "video", "start_at": pos_sec},
                on_state_change=persist)
```

- JS monta `<video>`/`<audio>` em `parentElement`, busca `data.start_at` em `loadedmetadata`
  e escuta `timeupdate`/`ended`.
- Reporta `setStateValue({current, duration, percent, paused, ended})` com throttle de 1 s
  ou delta ≥ 1% — sem throttle gera rerun por frame.
- `on_state_change` faz upsert imediato em `media_state` e espelha em
  `st.session_state["_pending_media"]` (gravado de novo no início do próximo rerun).
- Regras: `percent ≥ 0.95` ou `ended` → `watched`; `0 < percent < 0.95` → `in_progress`;
  nunca tocado → `new`; `play_count += 1` no primeiro `timeupdate` de cada sessão.
- Imagens usam `st.image` (sem JS). Thumbnails: `<img src=url>` do media server.

## 6. Páginas

### `home.py` — Biblioteca
- Métricas: fontes, mensagens, mídias, tamanho total, % assistidas, itens em progresso.
- Gráficos: mensagens/mês, distribuição por `media_type`, top senders, tamanho por pasta.
- "Continuar assistindo" → vai ao player. Status dos últimos jobs.

### `sources.py` — Fontes
- Adicionar por caminho; **"Procurar no projeto"** varre por `backup.db`/`messages.json`.
- Re-escanear: contagens, tamanho real em disco, `missing_files`, rebuild do FTS.
- Ativar/desativar/remover (nunca apaga arquivos); testar acesso.
- Sem fontes: instrui a rodar `backup/backup.py`.

### `browse.py` — Mensagens
- Filtros: busca full-text (FTS5, fallback `LIKE`), datas, `media_type`, remetente,
  só texto/só mídia, status de progresso, favoritos.
- `st.dataframe` paginado (LIMIT/OFFSET, 50/pág.) com seleção de linha.
- Detalhe: texto completo em markdown, mídia inline,
  botões **Assistir / Favoritar / Anotar / Baixar / Abrir arquivo**.
- `st.download_button` com CSV/JSON do conjunto filtrado.

### `gallery.py` — Galeria
- Grid de cards com miniatura servida pelo media server; paginação.
- Mesmos filtros do `browse`; clique → detalhe + player; badge de `status` e barra de %.

### `player.py` — Reprodutor
- Fila = resultado do filtro ativo (passado via `st.session_state`).
- Anterior/Próximo, retoma da posição salva (`start_at`), barra de % real.
- Marcar assistido/não assistido, nota, favorito.

### `jobs.py` — Executar backup/restore
- Formulário espelhando os CLIs (todas as opções de `backup.py` e `main.py`).
- Mostra a `.env` efetiva com `API_ID`/`API_HASH` mascarados; valida antes de rodar.
- `subprocess.Popen([sys.executable, "backup/backup.py", ...], cwd=<raiz do repo>)` —
  CWD na raiz para `OUTPUT_DIR=downloads` resolver em `<repo>/downloads` e os imports
  (`from config import ...`, `sys.path[0]=backup/`) funcionarem como no README.
- Log ao vivo via `@st.fragment(run_every=2s)`: tail incremental de stdout/log
  (`errors='replace'`) + barra (extrai `Progress: id=N`/tqdm; senão indeterminada).
- Cancelar (`terminate()` → `cancelled`), histórico com exit code, link para `log.txt`.

## 7. Configuração (`frontend/config.py`)

```
LIBRARY_DB   = frontend/library.db   (default)
MEDIA_HOST   = 127.0.0.1             (fixo; nunca 0.0.0.0)
MEDIA_PORT   = 0                     (efêmera)
PAGE_SIZE    = 50
WATCHED_AT   = 0.95                  (limiar de "assistido")
AUTO_SCAN    = true
```

## 8. Requisitos

```
streamlit>=1.65.0
pandas>=2.2
```

## 9. Execução

```bash
pip install -r frontend/requirements.txt
streamlit run frontend/streamlit_app.py
```

## 10. Critérios de aceite

1. Rodar sem nenhuma fonte cadastrada mostra instrução, sem erro.
2. "Procurar no projeto" registra `downloads/` automaticamente.
3. Busca por texto devolve resultados em < 1 s em 50k mensagens (FTS5).
4. Vídeo retoma exatamente de onde parou após fechar/reabrir o app.
5. `%` de progresso sobe durante a reprodução e vira `watched` aos 95%.
6. Imagem, áudio e download funcionam pelo mesmo media server.
7. Backup pode ser disparado da UI e o log aparece com atraso ≤ 2 s; cancelar mata o processo.
8. Nenhum arquivo/banco de conteúdo é modificado pelo frontend.
9. Nada escuta fora de `127.0.0.1`.
10. Tabelas nunca carregam mais de `PAGE_SIZE` linhas por vez.

## 11. Fora do escopo (v1)

Autenticação de usuário; acesso remoto; thumbnails com ffmpeg; edição de metadados do
canal; sincronização de `messages.json` de volta para o `backup.db`; testes de carga.

## 12. Riscos conhecidos

- Componente no DOM da página aponta `<video>` para o loopback (cross-origin):
  playback funciona e `Access-Control-Allow-Origin: *` cobre leitura de metadados.
- Banco de conteúdo travado durante backup: `mode=ro` + `busy_timeout`, fallback
  para `messages.json`.
- `media_path` quebrado (pasta movida/CWD diferente): normalização no scan +
  contagem `missing_files`.
- Log binário/no-UTF8 do tqdm no Windows: decodificação incremental com
  `errors="replace"`.
- Throttle do player: salvar no máximo 1×/s, senão o app fica lento.
