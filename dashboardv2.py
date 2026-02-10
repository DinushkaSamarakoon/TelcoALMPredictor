# dashboard_pro.py
# Professional NOC Alarm Prediction Dashboard with multi-file upload + auto-email routing
import os, io, ssl, hashlib
import pandas as pd
import streamlit as st
import altair as alt
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import smtplib
from datetime import datetime

from detecterv5 import predict_future_faults  # uses your trained model/encoders

# ──────────────────────────────────────────────────────────────
# Page + Theme
# ──────────────────────────────────────────────────────────────
st.set_page_config(page_title="NOC Proactive Intelligence Dashboard", layout="wide", page_icon="🚨")

st.markdown("""
<style>
.block-container { padding-top: 1rem; padding-bottom: 0.5rem; }
.kpi {border:1px solid #e5e7eb;border-radius:12px;padding:12px 16px;background:#fff;}
.kpi .label{color:#6b7280;font-size:0.85rem;}
.kpi .value{font-size:1.4rem;font-weight:700;}
.dataframe td, .dataframe th { font-size: 0.92rem; }
</style>
""", unsafe_allow_html=True)

st.title("📡 NOC Proactive Intelligence Command Center")
st.caption("Batch ingest alarms → predict future faults → route to responsible teams with a click (or automatically).")
st.markdown("---")

# ──────────────────────────────────────────────────────────────
# Email routing (YOUR recipients)
# ──────────────────────────────────────────────────────────────
# Any predicted team string containing these tokens will route to these addresses.
TEAM_RECIPIENTS = {
    "noc":    ["sahansa985@gmail.com"],
    "power":  ["shandinu98@gmail.com"],
    "field":  ["sahansa@mobitel.lk"],
}

def recipients_for_team(team_text: str):
    t = (team_text or "").lower()
    rcpts = set()
    if "noc" in t:    rcpts.update(TEAM_RECIPIENTS["noc"])
    if "power" in t:  rcpts.update(TEAM_RECIPIENTS["power"])
    if "field" in t:  rcpts.update(TEAM_RECIPIENTS["field"])
    # Fallback: if model yielded unknown team, default to NOC
    if not rcpts:
        rcpts.update(TEAM_RECIPIENTS["noc"])
    return sorted(rcpts)

# SMTP configuration via environment (recommended) or Streamlit secrets
SMTP_HOST = os.getenv("SMTP_HOST", st.secrets.get("SMTP_HOST", ""))
SMTP_PORT = int(os.getenv("SMTP_PORT", st.secrets.get("SMTP_PORT", 587)))
SMTP_USER = os.getenv("SMTP_USER", st.secrets.get("SMTP_USER", ""))
SMTP_PASS = os.getenv("SMTP_PASS", st.secrets.get("SMTP_PASS", ""))
SMTP_FROM = os.getenv("SMTP_FROM", st.secrets.get("SMTP_FROM", SMTP_USER))

EMAIL_ENABLED = bool(SMTP_HOST and SMTP_FROM)

def send_html_email(to_list, subject, html_body):
    if not EMAIL_ENABLED:
        st.warning("Email not configured. Set SMTP_* env vars or Streamlit secrets.")
        return False
    msg = MIMEMultipart("alternative")
    msg["From"] = SMTP_FROM
    msg["To"] = ", ".join(to_list)
    msg["Subject"] = subject
    msg.attach(MIMEText(html_body, "html"))
    try:
        context = ssl.create_default_context()
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as server:
            server.starttls(context=context)
            if SMTP_USER and SMTP_PASS:
                server.login(SMTP_USER, SMTP_PASS)
            server.send_message(msg)
        return True
    except Exception as e:
        st.error(f"Email failed: {e}")
        return False

def df_html_table(df: pd.DataFrame, max_rows=60):
    cols = ["Site", "Location", "Fault", "Probability (%)", "Risk Level", "Recommendation", "Team"]
    present = [c for c in cols if c in df.columns]
    show = df[present].head(max_rows).copy()
    return show.to_html(index=False, escape=False)

# ──────────────────────────────────────────────────────────────
# Sidebar: Upload + Options
# ──────────────────────────────────────────────────────────────
st.sidebar.header("📥 Data Ingestion")
uploaded_files = st.sidebar.file_uploader(
    "Upload alarm logs (CSV/XLSX) — multiple allowed",
    type=["csv", "xlsx", "xls"],
    accept_multiple_files=True
)

st.sidebar.header("✉️ Notification Settings")
auto_send = st.sidebar.toggle("Auto-send emails after prediction", value=False,
                              help="Automatically route results to teams as soon as predictions are ready.")
group_by_team = st.sidebar.toggle("Group emails by team", value=True)
max_rows_email = st.sidebar.number_input("Max rows per email", min_value=10, max_value=2000, value=200, step=10)
subject_prefix = st.sidebar.text_input("Email subject prefix", value="[NOC] AI Predicted Faults")

st.sidebar.markdown("---")
if EMAIL_ENABLED:
    st.sidebar.success(f"Email via {SMTP_HOST} as {SMTP_FROM}")
else:
    st.sidebar.warning("Email is disabled. Configure SMTP_HOST/PORT/USER/PASS/FROM.")

# maintain a simple “already sent” cache in session to limit duplicates
if "sent_signatures" not in st.session_state:
    st.session_state.sent_signatures = {}

# ──────────────────────────────────────────────────────────────
# Data Loader (multi-file + Excel sheet merge)
# ──────────────────────────────────────────────────────────────
def read_any(path_or_bytes, name: str) -> pd.DataFrame:
    name = name.lower()
    try:
        if name.endswith(".csv"):
            return pd.read_csv(path_or_bytes, engine="python", sep=None, on_bad_lines="skip")
        elif name.endswith((".xlsx", ".xls")):
            x = pd.ExcelFile(path_or_bytes)
            frames = [x.parse(s) for s in x.sheet_names]  # merge all sheets
            return pd.concat(frames, ignore_index=True)
        else:
            return pd.DataFrame()
    except Exception as e:
        st.error(f"Failed to read {name}: {e}")
        return pd.DataFrame()

def load_batch(files) -> pd.DataFrame:
    if not files:
        return pd.DataFrame()
    frames = []
    for f in files:
        df = read_any(f, f.name)
        if not df.empty:
            frames.append(df)
    if not frames:
        return pd.DataFrame()
    raw = pd.concat(frames, ignore_index=True)
    return raw

# ──────────────────────────────────────────────────────────────
# Main flow: ingest → predict → UI → email
# ──────────────────────────────────────────────────────────────
raw_df = load_batch(uploaded_files)
if raw_df.empty:
    st.info("👈 Upload one or more CSV/Excel files to begin.")
    st.stop()

with st.spinner("Analyzing uploaded alarms…"):
    results = predict_future_faults(raw_df)

if not results:
    st.warning("No significant future fault risk detected in this batch.")
    st.stop()

df = pd.DataFrame(results)

# ── KPI cards ────────────────────────────────────────────────
c1, c2, c3, c4 = st.columns(4)
c1.markdown(f"<div class='kpi'><div class='label'>Total Predictions</div><div class='value'>{len(df)}</div></div>", unsafe_allow_html=True)
c2.markdown(f"<div class='kpi'><div class='label'>HIGH Risk</div><div class='value'>{(df['Risk Level']=='HIGH').sum()}</div></div>", unsafe_allow_html=True)
c3.markdown(f"<div class='kpi'><div class='label'>Affected Sites</div><div class='value'>{df['Site'].nunique()}</div></div>", unsafe_allow_html=True)
avg_prob = round(df['Probability (%)'].mean(), 1) if 'Probability (%)' in df else 0
c4.markdown(f"<div class='kpi'><div class='label'>Avg Probability</div><div class='value'>{avg_prob}%</div></div>", unsafe_allow_html=True)

st.markdown("---")

# ── Filters ──────────────────────────────────────────────────
left, right = st.columns([2,1])
with left:
    st.subheader("📊 Fault Risk Overview")
    # bar: probability by fault
    bar = alt.Chart(df).mark_bar().encode(
        x=alt.X("Fault:N", sort="-y"),
        y="Probability (%):Q",
        color=alt.Color("Risk Level:N", scale=alt.Scale(domain=["LOW","MEDIUM","HIGH"],
                                                       range=["#2ecc71","#f1c40f","#e74c3c"])),
        tooltip=list(df.columns)
    ).properties(height=340)
    st.altair_chart(bar, use_container_width=True)

with right:
    st.subheader("🧭 Department Load")
    pie = alt.Chart(df).mark_arc().encode(
        theta="count()",
        color="Team:N",
        tooltip=["Team","count()"]
    ).properties(height=340)
    st.altair_chart(pie, use_container_width=True)

# ── Data view + quick filters ────────────────────────────────
st.subheader("📑 Intelligence Report & Recommendations")
f1, f2, f3 = st.columns(3)
site_filter = f1.multiselect("Site(s)", sorted(df["Site"].unique()))
risk_filter = f2.multiselect("Risk Level", ["LOW","MEDIUM","HIGH"], default=["LOW","MEDIUM","HIGH"])
team_text = f3.text_input("Team contains", value="")

view = df.copy()
if site_filter:
    view = view[view["Site"].isin(site_filter)]
if risk_filter:
    view = view[view["Risk Level"].isin(risk_filter)]
if team_text:
    view = view[view["Team"].str.contains(team_text, case=False, na=False)]

st.dataframe(view.style.background_gradient(subset=["Probability (%)"], cmap="YlOrRd"),
             use_container_width=True, hide_index=True)

st.markdown("---")

# ── Action Center ────────────────────────────────────────────
colA, colB = st.columns(2)
with colA:
    if st.button("📧 Send Emails to Responsible Teams"):
        sent_count = 0
        if group_by_team:
            for team, grp in view.groupby("Team"):
                to_list = recipients_for_team(team)
                html = df_html_table(grp, max_rows=max_rows_email)
                # de-dup per team (hash by data & team)
                sig = hashlib.sha256((team + grp.to_csv(index=False)).encode()).hexdigest()
                if st.session_state.sent_signatures.get(team) == sig:
                    st.info(f"Skipped {team}: already sent this content.")
                    continue
                ok = send_html_email(to_list, f"{subject_prefix} — {team} ({len(grp)})", html)
                if ok:
                    st.session_state.sent_signatures[team] = sig
                    sent_count += 1
        else:
            to_all = []
            for t in view["Team"].fillna("").unique():
                to_all += recipients_for_team(t)
            to_all = sorted(set(to_all))
            html = df_html_table(view, max_rows=max_rows_email)
            ok = send_html_email(to_all, f"{subject_prefix} — {len(view)} items", html)
            if ok:
                sent_count = 1
        if sent_count:
            st.success(f"Emails sent: {sent_count}")
        else:
            st.warning("No emails sent.")

with colB:
    st.download_button("⬇️ Export Predictions (CSV)", data=view.to_csv(index=False),
                       file_name=f"Predictions_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv",
                       mime="text/csv")

# ── Auto-send if enabled ─────────────────────────────────────
if auto_send:
    # same logic as button but silent
    for team, grp in view.groupby("Team"):
        to_list = recipients_for_team(team)
        html = df_html_table(grp, max_rows=max_rows_email)
        sig = hashlib.sha256((team + grp.to_csv(index=False)).encode()).hexdigest()
        if st.session_state.sent_signatures.get(team) == sig:
            continue
        ok = send_html_email(to_list, f"{subject_prefix} — {team} ({len(grp)})", html)
        if ok:
            st.session_state.sent_signatures[team] = sig
    st.info("Auto-send processed. (Duplicates are skipped by signature.)")
