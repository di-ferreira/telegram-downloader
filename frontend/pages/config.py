from __future__ import annotations

import streamlit as st

from core import envfile, preflight

st.title("⚙️ Configurações do backend")
st.caption(
    "`backup/` e `restore/` leem o `.env` **da raiz do repositório** (rodam com "
    "`cwd=<raiz>`), então este é o arquivo único de configuração. "
    "Nenhum segredo é exibido por inteiro aqui — campos vazios mantêm o valor atual."
)

# ------------------------------------------------------------------ status
st.subheader("🩺 Status")


def _status_block(tool: str, label: str) -> None:
    rows = preflight.report(tool)
    with st.container(border=True):
        st.markdown(f"**{label}**")
        for row in rows:
            icon = {"ok": "🟢", "warn": "🟡", "error": "🔴"}[row["level"]]
            line = f"{icon} {row['message']}"
            if row["level"] != "ok" and row.get("fix"):
                line += f"  \n`{row['fix']}`"
            st.markdown(line)


c1, c2 = st.columns(2)
with c1:
    _status_block("backup", "Backup")
with c2:
    _status_block("restore", "Restore")

if not envfile.exists():
    if st.button("➕ Criar `.env` a partir dos exemplos", type="primary"):
        envfile.ensure()
        st.rerun()
    st.stop()

# ------------------------------------------------------- conta / sessão
st.markdown("---")
st.subheader("🔑 Conta do Telegram")
session_file = preflight.session_path()
st.caption(
    f"Sessão: `{session_file.name}` · "
    + ("🟢 pronta" if session_file.exists() else "🔴 pendente — o 1º login é interativo")
)

with st.form("cfg_account"):
    a1, a2 = st.columns(2)
    with a1:
        api_id = st.text_input(
            "API_ID", value=envfile.get("API_ID"), key="cfg_api_id",
            help="my.telegram.org/apps",
        )
    with a2:
        api_hash = st.text_input(
            "API_HASH", type="password", key="cfg_api_hash",
            placeholder=envfile.mask("API_HASH", envfile.get("API_HASH")) or "não definido",
            help="Deixe em branco para manter o valor atual.",
        )
    session_name = st.text_input(
        "SESSION_NAME (compartilhado pelas duas ferramentas)",
        value=envfile.session_name(), key="cfg_session",
    )
    submitted_account = st.form_submit_button("💾 Salvar conta/sessão", type="primary")

if submitted_account:
    updates: dict[str, str] = {"SESSION_NAME": session_name.strip() or envfile.DEFAULTS["SESSION_NAME"]}
    if api_id.strip():
        try:
            int(api_id.strip())
        except ValueError:
            st.error("API_ID precisa ser numérico.")
            st.stop()
        updates["API_ID"] = api_id.strip()
    if api_hash.strip():
        updates["API_HASH"] = api_hash.strip()
    envfile.write(updates)
    st.success("Salvo.")
    st.rerun()

if not session_file.exists():
    st.code("python frontend/login.py", language="bash")
    st.caption("Rode em um terminal na raiz do repositório — pede telefone e código uma vez.")

# ---------------------------------------------------------------- backup
st.markdown("---")
st.subheader("📦 Backup")

with st.form("cfg_backup"):
    b1, b2 = st.columns(2)
    with b1:
        channel = st.text_input(
            "CHANNEL", value=envfile.get("CHANNEL"), key="cfg_channel",
            help="@username, -100… ou link de convite",
        )
    with b2:
        output_dir = st.text_input(
            "OUTPUT_DIR", value=envfile.get("OUTPUT_DIR") or envfile.DEFAULTS["OUTPUT_DIR"],
            key="cfg_output", help="Relativo à raiz do repositório.",
        )
    concurrent = st.number_input(
        "CONCURRENT_DOWNLOADS", min_value=1, max_value=32,
        value=int(envfile.get("CONCURRENT_DOWNLOADS") or 5), step=1, key="cfg_conc",
    )
    submitted_backup_cfg = st.form_submit_button("💾 Salvar configuração do backup", type="primary")

if submitted_backup_cfg:
    envfile.write(
        {
            "CHANNEL": channel.strip(),
            "OUTPUT_DIR": output_dir.strip() or "downloads",
            "CONCURRENT_DOWNLOADS": str(int(concurrent)),
        }
    )
    st.success("Salvo.")
    st.rerun()

# ---------------------------------------------------------------- restore
st.markdown("---")
st.subheader("♻️ Restore")

with st.form("cfg_restore"):
    phone = st.text_input(
        "PHONE (com código do país)", type="password", key="cfg_phone",
        placeholder=envfile.mask("PHONE", envfile.get("PHONE")) or "+55…",
        help="Deixe em branco para manter o valor atual.",
    )
    r1, r2 = st.columns(2)
    with r1:
        channel_name = st.text_input(
            "CHANNEL_NAME", value=envfile.get("CHANNEL_NAME"), key="cfg_rname",
            help="Nome do canal criado pelo restore.",
        )
    with r2:
        channel_username = st.text_input(
            "CHANNEL_USERNAME", value=envfile.get("CHANNEL_USERNAME"), key="cfg_ruser",
            help="Opcional; deixe vazio para sem @.",
        )
    channel_desc = st.text_input(
        "CHANNEL_DESCRIPTION", value=envfile.get("CHANNEL_DESCRIPTION"), key="cfg_rdesc",
    )
    backup_folder = st.text_input(
        "BACKUP_FOLDER", value=envfile.get("BACKUP_FOLDER") or envfile.DEFAULTS["BACKUP_FOLDER"],
        key="cfg_rfolder", help="Pasta lida pelo restore (relativa à raiz).",
    )
    submitted_restore_cfg = st.form_submit_button("💾 Salvar configuração do restore", type="primary")

if submitted_restore_cfg:
    updates = {
        "CHANNEL_NAME": channel_name.strip(),
        "CHANNEL_USERNAME": channel_username.strip(),
        "CHANNEL_DESCRIPTION": channel_desc.strip(),
        "BACKUP_FOLDER": backup_folder.strip() or "downloads",
    }
    if phone.strip():
        updates["PHONE"] = phone.strip()
    envfile.write(updates)
    st.success("Salvo.")
    st.rerun()

# ---------------------------------------------------------------- arquivo
st.markdown("---")
with st.expander("📄 Ver `.env` (valores sensíveis mascarados)"):
    st.json(envfile.preview(), expanded=False)
    st.caption(f"Arquivo: `{envfile.ENV_PATH}` · backup automático: `.env.bak` a cada gravação.")
    st.caption(
        "As duas ferramentas leem este mesmo arquivo. Se você rodar um script com "
        "outra pasta como diretório corrente, ele passa a ler o `.env` daquela pasta."
    )
