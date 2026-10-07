# SPEC-BACKEND — Configurações e funcionalidades de `backup/` e `restore/`

Complementa a [`SPEC.md`](SPEC.md) (biblioteca/mídia/busca) com o que o frontend
precisa para **configurar e operar** as duas ferramentas de linha de comando.
Escopo, contrato e decisões abaixo; o que já existia (fila, log ao vivo,
cancelamento) continua descrito na SPEC original.

## 0. Decisões (aprovadas)

| Tema | Decisão |
|---|---|
| Onde configurar | **Um único `.env` na raiz** — `backup/config.py` e `restore/config.py` leem `Path.cwd()/".env"` antes do próprio diretório, e os jobs rodam com `cwd = raiz`, então vale para as duas ferramentas |
| Entrega | Spec **+** implementação |
| Estrutura | **Páginas novas `Config` e `Backends`**; `jobs.py` continua sendo fila/log |
| Sem console | Preflight **bloqueia com instruções** quando faltar `.env`, dependências ou `.session`; o login interativo fica em CLI (`frontend/login.py`), nunca na UI |
| Sessão | Os dois exemplos definem `SESSION_NAME` (`telegram_backup` vs `telegram_restore`); por ser um arquivo só, vale **`telegram_session`** compartilhado |
| Restore real | Exige **confirmação explícita** no formulário (cria canal novo) |

## 1. Contrato do backend observado

### 1.1 `backup/backup.py`

- Flags espelhadas no formulário: `--start-date`, `--end-date`, `--media-type`,
  `--skip-existing`/`--no-skip-existing`, `--resume`/`--no-resume`,
  `--no-sqlite`, `--message-ids`, `--only-media`, `--only-text`,
  `--list-channels [--save]`.
- Saídas em `OUTPUT_DIR` (padrão `downloads/`): `backup.db`, `messages.json`,
  `messages.csv`, `log.txt`, `media/{photos,videos,documents,audios,gifs,
  stickers,others}/`; além disso `backup/channels.txt` com
  `--list-channels --save`.
- **`--no-sqlite` é parsed mas nunca usado**: `export_sqlite()` não é chamado em
  nenhum caminho. A opção existe na UI com aviso no `help` de que hoje é no-op.

### 1.2 `restore/main.py`

- Flags: `--backup-folder`, `--start-date/--end-date`, `--start-id/--end-id`,
  `--only-media/--only-text`, `--media-type`, `--retry-errors --channel-id`,
  `--dry-run`.
- Comportamentos que a UI precisa refletir:
  - **Cria um canal novo a cada execução** (exceto em retry, que reutiliza o
    `channel_id`) → confirmação obrigatória para rodar de verdade.
  - `--dry-run` **não faz login** (o resume roda antes do `await login()`), só
    imprime métricas no stdout → pode ser simulado sem `.session`.
  - `restore_progress.db` e `logs/{restore,errors,missing_media}.log` são
    relativos ao cwd (= raiz do repositório) → lidos apenas para exibição.
  - Throttle embutido de 2–5 s por mensagem e 30–60 s a cada 20.

## 2. `.env` da raiz

Módulo: `frontend/core/envfile.py`. Arquivo: `REPO_ROOT/.env`.

| Conceito | Detalhe |
|---|---|
| Criação | `ensure()` monta o arquivo a partir de `backup/.env.example` + `restore/.env.example`, mantendo comentários e seções |
| Chaves obrigatórias | backup: `API_ID`, `API_HASH`, `CHANNEL` · restore: `API_ID`, `API_HASH`, `PHONE`, `CHANNEL_NAME` |
| Placeholders | `123456`, `your_api_hash_here`, `@channel_username`, `+5511999999999`, `My Restored Channel` contam como **não preenchidos** (`envfile.missing()`) |
| Sessão | `SESSION_NAME=telegram_session` é aplicada no primeiro `write` (o backup example venceria por ordem de leitura) |
| Gravação | Merge preservando comentários/outras chaves, sem duplicar chave, atômico (`<tmp>` + `os.replace`), com backup automático `.env.bak` |
| Segredos | `API_HASH` e `PHONE` nunca aparecem inteiros (`preview()`/`mask()`); `job_runner.env_preview` delega a essa função |

Arquivos `.env`, `.env.bak` e `.env.tmp` estão no `.gitignore`.

## 3. Preflight — `frontend/core/preflight.py`

`{level, code, message, fix}` — `error` bloqueia o submit, `warn` só avisa.

| code | quando | fix (exibido em código) |
|---|---|---|
| `env_missing` | sem `.env` na raiz | `Criar na página Configurações.` |
| `env_incomplete` | chaves obrigatórias ausentes/placeholders | `Preencher na página Configurações.` |
| `deps_missing` | `telethon`/`tqdm`/`dotenv` ausentes | `pip install -r backup/requirements.txt` |
| `session_missing` | `<SESSION_NAME>.session` inexistente | `python frontend/login.py backup` |
| `folder_missing` / `folder_empty` | `BACKUP_FOLDER` inexistente ou sem `backup.db`/`messages.json` | `Rodar um backup antes.` |
| `exclusive` | `--only-media` + `--only-text` | — |
| `retry_channel` | `--retry-errors` sem `--channel-id` | — |
| `date_order` | data inicial > final | — |
| `list_ignored` (warn) | `--list-channels` com filtro de conteúdo | — |

- `for_backup(opts)` / `for_restore(opts)` = checagens do ambiente;
  `validate_backup_opts` / `validate_restore_opts` = regras do formulário.
- Em `dry_run` a sessão **degrada para `warn`** (`restore` não loga) e a pasta
  continua sendo `error` (o arquivo é obrigatório).
- `report(tool)` = linhas de status da página Configurações.
- `session_path()` resolve `<SESSION_NAME>` contra `REPO_ROOT` com sufixo
  `.session` — mesmo caminho que os dois tools resolvem pelo cwd.

## 4. Arquitetura

```
frontend/
├── SPEC-BACKEND.md                 # este documento
├── login.py                        # CLI: cria <SESSÃO>.session (1º acesso)
├── core/
│   ├── envfile.py                  # .env da raiz: ler/mascarar/merge/atomic write
│   ├── preflight.py                # checagens pré-job + validações de formulário
│   └── backend_state.py            # leitura read-only de artefatos do backend
├── components/ui.py                # page_link() tolerante fora da navegação
├── pages/
│   ├── config.py                   # ⚙️ Configurações (novo)
│   ├── backends.py                 # 🔌 Backends (novo)
│   └── jobs.py                     # fila/log + gating de preflight (ajustado)
└── streamlit_app.py                # navegação registra as duas páginas
```

### 4.1 `backend_state.py` (somente leitura)

- `output_dir()` / `backup_artifacts()` — `backup.db`, `messages.json`/`csv`,
  `log.txt`, `media/`, `channels.txt` com contagens.
- `parse_channels()` / `saved_channels()` — tabela `--list-channels`.
- `parse_dry_run()` — métricas do stdout do `--dry-run` (total, mídia, tamanho,
  faltantes), tolerando separador de milhar.
- `restore_progress()` — `restore_progress.db` (`mode=ro`): contagens, erros,
  `last_sent`.
- `restore_logs()` / `read_tail()` — `logs/{restore,errors,missing_media}.log`.

Nada aqui escreve fora do frontend; o único arquivo **mutável** pelo frontend é
o `.env` da raiz.

## 5. Páginas

### 5.1 Configurações (`pages/config.py`)

1. **Status** por ferramenta (`preflight.report`): bibliotecas, `.env`, sessão.
2. **Criar `.env`** quando ausente.
3. **Conta**: `API_ID`, `API_HASH` (password, placeholder já mascarado),
   `SESSION_NAME` + comando de login.
4. **Backup**: `CHANNEL`, `OUTPUT_DIR`, `CONCURRENT_DOWNLOADS`.
5. **Restore**: `PHONE`, `CHANNEL_NAME`, `CHANNEL_USERNAME`,
   `CHANNEL_DESCRIPTION`, `BACKUP_FOLDER`.
6. Expander com o `.env` atual mascarado.

Gravações usam `envfile.write()` (merge + `.env.bak`); o submit também recalcula
`missing()` para avisar imediatamente.

### 5.2 Backends (`pages/backends.py`)

Tudo que **executa** o backend, com `_dispatch(kind, opts, purpose)`:
preflight → `job_runner.start_job(cwd=REPO_ROOT)` → `st.session_state` → rerun.

- **Job ativo** (`@st.fragment(run_every=…)` só enquanto roda): status, log e
  cancelamento; um dry-run concluído materializa o resultado parseado.
- **📡 Canais** — `--list-channels --save` → tabela + "aplicar em `CHANNEL`".
- **📦 Saídas do backup** — artefatos, `log.txt`, "registrar/escanear fonte"
  (`content.detect` + `registry.add_source` + `scan_source`).
- **🧪 Simular restore** — `--dry-run` → métricas e arquivos faltantes.
- **📊 Progresso do restore** — `restore_progress.db` + tabela de erros com
  "repetir estes erros" (usa o `channel_id`).
- **🗂️ Logs** — tails + download.

### 5.3 Backup & Restore (`pages/jobs.py`)

- `_show_blockers(tool, opts)` renderiza o preflight **dentro da coluna** e o
  submit nasce `disabled=True` quando há `error`.
- No submit, o preflight completo (ambiente + formulário) roda de novo antes de
  `start_job`; qualquer `error` → `st.stop()`.
- Novo checkbox `--no-sqlite` com aviso de que é no-op hoje.
- Restore real exige `confirm_restore` marcado.
- Link para Configurações quando há bloqueio e para `Backends` no topo.

`components/ui.page_link()` envolve `st.page_link`: fora de `st.navigation`
(ex.: teste que roda a página isolada) vira legenda em vez de exceção.

## 6. Limitações assumidas

1. `--no-sqlite` não tem efeito no backend atual (interface espelha a CLI).
2. Um restore real **cria canal** — mitigado por confirmação, não por preflight.
3. `restore_progress.db` e `logs/` são lidos sem trava: um restore em execução
   pode ser visto a meio caminho.
4. Credenciais ficam em texto no `.env` (mesma realidade do backend); a UI só
   evita exibi-las.
5. `channel_id` precisa ser digitado à mão (o retry pede um valor que a UI não
   descobre sozinha — o progresso exibe o canal atual).

## 7. Critérios de aceite

1. Sem `.env`, Configurações mostra como criar; Backends/Jobs bloqueiam o submit
   com o comando exato (nada de stack trace).
2. Com `.env` de exemplo intacto (placeholders), `env_incomplete` aponta
   `API_ID, API_HASH, CHANNEL` (backup) e `PHONE, CHANNEL_NAME` (restore).
3. Sem `telethon`, o fix exibido é `pip install -r backup/requirements.txt`.
4. Sem `.session`, o fix é `python frontend/login.py backup` (ou `restore`);
   `login.py` sem credenciais sai com código 2 e mensagem clara.
5. Dry-run de restore roda **sem** `.session`, desde que a pasta tenha
   `backup.db`/`messages.json`.
6. `SESSION_NAME` criado pelo frontend vale para os dois tools.
7. Gravar configuração preserva comentários, cria `.env.bak` e não duplica chave.
8. `API_HASH`/`PHONE` nunca aparecem inteiros na interface.
9. Backup/restore só disparam com preflight verde; `--no-sqlite` aparece no argv.
10. Restore real sem a confirmação marcada não dispara nada.
11. A página Backends sozinha não cria job nenhum (dry-run bloqueado pastamalformada/ausente).

## 8. Verificação

```powershell
pip install -r backup/requirements.txt -r restore/requirements.txt   # telethon etc.
python -m pyflakes frontend
python -m compileall -q frontend
python frontend/login.py            # sem credenciais -> exit 2
python frontend/login.py backup     # interativo, cria <SESSÃO>.session
streamlit run frontend/streamlit_app.py
```

Suítes automatizadas (fora do repositório, em `%TEMP%\opencode\`):
`backend_test.py` (envfile/preflight/argv/parsers/AppTest das 2 páginas novas),
`smoke_test.py`, `interact_test.py` (inclui o gating de jobs),
`progress_test.py`, `perf_test.py`.
