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
# Updated with your specific recipient list
TEAM_EMAILS = {
    "Field": "sahansa985@gmail.com",
    "NOC": "shandinu98@gmail.com",
    "Power": "sahansa@mobitel.lk"
}

# ================= SIDEBAR: MULTI-FILE UPLOAD =================
st.sidebar.header("📥 Data Ingestion")
# Supports uploading multiple Excel/CSV files simultaneously
uploaded_files = st.sidebar.file_uploader(
    "Upload Alarm Logs (Batch Processing)", 
    type=["csv", "xlsx"], 
    accept_multiple_files=True
)

# ================= AUTOMATIC EMAIL ROUTING LOGIC =================
def auto_dispatch_emails(df):
    sender_email = "telcoalarmpredictorv1@gmail.com"
    sender_password = "bgdajtjpxuudvnmh" # Ensure App Password is used
    
    # Identify unique teams present in the prediction results
    active_teams = df['Team'].unique()
    dispatched_count = 0
    
    for team in active_teams:
        if team in TEAM_EMAILS:
            receiver_email = TEAM_EMAILS[team]
            team_df = df[df['Team'] == team]
            
            body = f"URGENT: Proactive Maintenance Required for {team}\n\n"
            body += "The AI system has predicted the following future faults for your department:\n\n"
            
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
            msg["Subject"] = f"🚨 AI Maintenance Alert: {team} Department"
            msg.attach(MIMEText(body, "plain"))

            try:
                with smtplib.SMTP("smtp.gmail.com", 587, timeout=20) as server:
                    server.starttls()
                    server.login(sender_email, sender_password)
                    server.send_message(msg)
                st.sidebar.success(f"✅ Dispatched to {team} ({receiver_email})")
                dispatched_count += 1
            except Exception as e:
                st.sidebar.error(f"❌ Failed to reach {team}: {e}")
    
    return dispatched_count

# ================= MAIN LOGIC =================
if uploaded_files:
    try:
        # Batch Processing: Combine all uploaded files into one DataFrame
        all_dfs = []
        for file in uploaded_files:
            if file.name.endswith(".csv"):
                temp_df = pd.read_csv(file, engine="python", sep=None, on_bad_lines="skip")
            else:
                temp_df = pd.read_excel(file)
            all_dfs.append(temp_df)
        
        raw_df = pd.concat(all_dfs, ignore_index=True)

        with st.spinner("Analyzing Batch Data..."):
            results = predict_future_faults(raw_df)

        if not results:
            st.warning("No significant future fault risk detected.")
            st.stop()

        results_df = pd.DataFrame(results)

        # --- AUTOMATION: Auto-send emails immediately after prediction ---
        # Note: In a production UI, you might want a toggle for this.
        if "emails_sent" not in st.session_state:
            with st.spinner("Automating Email Dispatches..."):
                count = auto_dispatch_emails(results_df)
                st.session_state["emails_sent"] = True
                st.toast(f"Automated alerts sent to {count} teams!")

        # --- KPI METRIC CARDS ---
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total Predictions", len(results_df))
        col2.metric("Critical Risks (High)", len(results_df[results_df["Risk Level"] == "HIGH"]))
        col3.metric("Affected Sites", results_df["Site"].nunique())
        col4.metric("Avg. Probability", f"{round(results_df['Probability (%)'].mean(), 1)}%")

        st.markdown("---")

        # --- VISUAL ANALYTICS & DATA VIEW ---
        # (Standard filtering and display logic remains same as original)
        st.subheader("📋 Intelligence Report")
        st.dataframe(results_df.style.background_gradient(subset=["Probability (%)"], cmap="YlOrRd"), use_container_width=True)

        # --- MANUAL EXPORT ---
        st.download_button("📥 Export NOC Master Report (CSV)", results_df.to_csv(index=False), "NOC_Report.csv", "text/csv")

    except Exception as e:
        st.error(f"Critical System Error: {e}")
else:
    # Clear session state if files are removed
    if "emails_sent" in st.session_state:
        del st.session_state["emails_sent"]

    st.info("👈 Dashboard Idle. Please upload alarm logs in the sidebar to begin.")
