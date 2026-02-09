import streamlit as st
import pandas as pd
from detecterv5 import predict_future_faults
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import altair as alt

# --- PROFESSIONAL NOC CONFIGURATION ---
st.set_page_config(page_title="NOC Proactive Intelligence Dashboard", layout="wide")

st.title("📡 NOC Proactive Intelligence Command Center")
st.markdown("---")

# ================= EMAIL ROUTING CONFIGURATION =================
# Maps team names to their departmental emails. 
# The system will automatically send the right data to the right team.
TEAM_EMAILS = {
    "Field Team": "shandinu98@gmail.com",
    "NOC Team": "noc.alerts@company.com",
    "Power Team": "sahansa985.com",
    "RAN Team": "ran.maintenance@company.com",
    "Transmission Team": "sahansa@mobitel.lk"
}

# ================= SIDEBAR: MULTI-FILE UPLOAD =================
st.sidebar.header("📥 Data Ingestion")
# Upgrade: Multi-file selection enabled as per supervisor request
uploaded_files = st.sidebar.file_uploader(
    "Upload Alarm Logs (Batch Processing)", 
    type=["csv", "xlsx"], 
    accept_multiple_files=True
)

# ================= AUTOMATIC EMAIL ROUTING LOGIC =================
def auto_dispatch_emails(df):
    sender_email = "telcoalarmpredictorv1@gmail.com"
    sender_password = "bgdajtjpxuudvnmh" # Use your 16-character Gmail App Password
    
    # Identify unique teams in the filtered results
    active_teams = df['Team'].unique()
    
    for team in active_teams:
        if team in TEAM_EMAILS:
            receiver_email = TEAM_EMAILS[team]
            team_df = df[df['Team'] == team]
            
            body = f"URGENT: Proactive Maintenance Required for {team}\n\n"
            body += "The AI system has predicted the following future faults for your site cluster:\n\n"
            
            for _, row in team_df.iterrows():
                body += (
                    f"📍 SITE: {row['Site']} ({row['Location']})\n"
                    f"⚠️ PREDICTED FAULT: {row['Fault']}\n"
                    f"📈 PROBABILITY: {row['Probability (%)']}%\n"
                    f"🔴 RISK LEVEL: {row['Risk Level']}\n"
                    f"🛠️ RECOMMENDATION: {row['Recommendation']}\n"
                    f"----------------------------------------\n"
                )

            msg = MIMEMultipart()
            msg["From"] = sender_email
            msg["To"] = receiver_email
            msg["Subject"] = f"🚨 AI Maintenance Alert: {team}"
            msg.attach(MIMEText(body, "plain"))

            try:
                with smtplib.SMTP("smtp.gmail.com", 587, timeout=20) as server:
                    server.starttls()
                    server.login(sender_email, sender_password)
                    server.send_message(msg)
                st.sidebar.success(f"✅ Dispatched to {team}")
            except Exception as e:
                st.sidebar.error(f"❌ Failed to reach {team}")

# ================= MAIN LOGIC =================
if uploaded_files:
    try:
        # Batch Processing: Combine all uploaded files into one analysis
        all_dfs = []
        for file in uploaded_files:
            temp_df = (
                pd.read_csv(file, engine="python", sep=None, on_bad_lines="skip")
                if file.name.endswith(".csv") else pd.read_excel(file)
            )
            all_dfs.append(temp_df)
        
        raw_df = pd.concat(all_dfs, ignore_index=True)

        with st.spinner("Analyzing Batch Data..."):
            results = predict_future_faults(raw_df)

        if not results:
            st.warning("No significant future fault risk detected.")
            st.stop()

        results_df = pd.DataFrame(results)

        # --- KPI METRIC CARDS ---
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total Predictions", len(results_df))
        col2.metric("Critical Risks (High)", len(results_df[results_df["Risk Level"] == "HIGH"]))
        col3.metric("Affected Sites", results_df["Site"].nunique())
        col4.metric("Avg. Probability", f"{round(results_df['Probability (%)'].mean(), 1)}%")

        st.markdown("---")

        # --- ADVANCED FILTERS (Sidebar) ---
        st.sidebar.header("🔍 Filtering & Search")
        site_filter = st.sidebar.multiselect("Select Site ID", options=sorted(results_df["Site"].unique()))
        team_filter = st.sidebar.multiselect("Responsible Team", options=sorted(results_df["Team"].unique()))
        risk_filter = st.sidebar.multiselect("Risk Category", options=["HIGH", "MEDIUM", "LOW"], default=["HIGH", "MEDIUM", "LOW"])

        # Apply logic
        filtered_df = results_df.copy()
        if site_filter: filtered_df = filtered_df[filtered_df["Site"].isin(site_filter)]
        if team_filter: filtered_df = filtered_df[filtered_df["Team"].isin(team_filter)]
        if risk_filter: filtered_df = filtered_df[filtered_df["Risk Level"].isin(risk_filter)]

        # --- VISUAL ANALYTICS ---
        v_col1, v_col2 = st.columns([2, 1])

        with v_col1:
            st.subheader("📊 Fault Risk Probability Trend")
            chart = alt.Chart(filtered_df).mark_bar().encode(
                x=alt.X("Fault:N", sort="-y", title="Fault Type"),
                y=alt.Y("Probability (%):Q", title="Probability (%)"),
                color=alt.Color("Risk Level:N", scale=alt.Scale(domain=["LOW", "MEDIUM", "HIGH"], range=["#2ecc71", "#f1c40f", "#e74c3c"])),
                tooltip=list(filtered_df.columns)
            ).properties(height=350)
            st.altair_chart(chart, use_container_width=True)

        with v_col2:
            st.subheader("🧮 Department Workload")
            team_pie = alt.Chart(filtered_df).mark_arc().encode(
                theta="count()",
                color="Team:N",
                tooltip=["Team", "count()"]
            ).properties(height=350)
            st.altair_chart(team_pie, use_container_width=True)

        # --- DATA VIEW (Professional Data Editor Fix) ---
        st.subheader("📋 Intelligence Report & Maintenance Recommendations")
        
        st.data_editor(
            filtered_df,
            column_config={
                "Probability (%)": st.column_config.ProgressColumn(
                    "Fault Probability",
                    help="Likelihood of the fault occurring",
                    format="%f%%",
                    min_value=0,
                    max_value=100,
                ),
                "Risk Level": st.column_config.TextColumn("Risk Level"),
                "Recommendation": st.column_config.TextColumn("Action Required", width="large")
            },
            use_container_width=True,
            disabled=True, 
            hide_index=True
        )

        # --- ACTION CENTER ---
        st.markdown("---")
        st.subheader("🚀 Operational Actions")
        
        a_col1, a_col2 = st.columns(2)
        
        with a_col1:
            # Automatic routing feature as per supervisor request
            if st.button("📢 Dispatch Smart Alerts to Responsible Teams"):
                auto_dispatch_emails(filtered_df)
        
        with a_col2:
            st.download_button(
                "📥 Export NOC Master Report (CSV)", 
                filtered_df.to_csv(index=False), 
                "NOC_Report.csv", 
                "text/csv"
            )

    except Exception as e:
        st.error(f"System Error: {e}")
else:
    st.info("👈 Dashboard Idle. Please upload one or more alarm logs in the sidebar to begin.")
