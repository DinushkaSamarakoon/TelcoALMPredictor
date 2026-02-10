import streamlit as st
import pandas as pd
from detecterv5 import predict_future_faults
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import altair as alt

# --- PROFESSIONAL NOC CONFIGURATION ---
st.set_page_config(page_title="TELCO Maintenance Portal", layout="wide")

# --- BACKGROUND IMAGE LINKS ---
header_bg = "https://raw.githubusercontent.com/DinushkaSamarakoon/TelcoALMPredictor/main/Gemini_Generated_Image_gx3ewvgx3ewvgx3e.png"
sidebar_bg = "https://raw.githubusercontent.com/DinushkaSamarakoon/TelcoALMPredictor/main/Gemini_Generated_Image_gx3ewvgx3ewvgx3e.png"

st.markdown(
    f"""
    <style>
    /* 1. TOP HEADER BOX STYLE */
    .top-header-box {{
        background-image: linear-gradient(rgba(0,0,0,0.5), rgba(0,0,0,0.5)), url("{header_bg}");
        background-size: cover;
        background-position: center;
        padding: 30px;
        border-radius: 15px;
        margin-bottom: 20px;
        color: white;
    }}
    .top-header-box h1 {{ color: white !important; margin: 0; }}

    /* 2. LEFT SIDEBAR PANEL STYLE */
    [data-testid="stSidebar"] {{
        background-image: linear-gradient(rgba(0,0,0,0.7), rgba(0,0,0,0.7)), url("{sidebar_bg}");
        background-size: cover;
        background-position: center;
    }}
    
    /* Ensure Sidebar text is readable */
    [data-testid="stSidebar"] p, [data-testid="stSidebar"] h2, [data-testid="stSidebar"] label {{
        color: white !important;
    }}
    </style>
    
    <div class="top-header-box">
        <h1>📡 TELCO Maintenance Portal</h1>
        <p>Proactive Intelligence Command Center</p>
    </div>
    """,
    unsafe_allow_html=True
)
# ================= EMAIL ROUTING CONFIGURATION =================
# Maps specific departments to your requested emails
TEAM_EMAILS = {
    "Field": "sahansa985@gmail.com",
    "NOC": "shandinu98@gmail.com",
    "Power": "sahansa@mobitel.lk"
}

# ================= SIDEBAR: MULTI-FILE UPLOAD =================
st.sidebar.header("📥 Data Ingestion")
uploaded_files = st.sidebar.file_uploader(
    "Upload Alarm Logs (Batch Processing)", 
    type=["csv", "xlsx"], 
    accept_multiple_files=True
)

# ================= AUTOMATIC EMAIL ROUTING LOGIC =================
def auto_dispatch_emails(df):
    sender_email = "telcoalarmpredictorv1@gmail.com"
    sender_password = "bgdajtjpxuudvnmh" # Ensure this is a valid App Password
    
    active_teams = df['Team'].unique()
    dispatched_count = 0
    
    for team in active_teams:
        if team in TEAM_EMAILS:
            receiver_email = TEAM_EMAILS[team]
            team_df = df[df['Team'] == team]
            
            body = f"URGENT: Proactive Maintenance Required for {team}\n\n"
            body += "The FDP system has predicted the following future faults for your department:\n\n"
            
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
            msg["Subject"] = f"🚨 TELCO Maintenance Alert: {team} Department"
            msg.attach(MIMEText(body, "plain"))

            try:
                with smtplib.SMTP("smtp.gmail.com", 587, timeout=20) as server:
                    server.starttls()
                    server.login(sender_email, sender_password)
                    server.send_message(msg)
                dispatched_count += 1
            except Exception as e:
                st.sidebar.error(f"❌ Failed to reach {team}: {e}")
    
    return dispatched_count

# ================= MAIN LOGIC (All chart logic must be inside here) =================
if uploaded_files:
    try:
        # 1. Process Files
        all_dfs = []
        for file in uploaded_files:
            temp_df = pd.read_csv(file, engine="python", sep=None) if file.name.endswith(".csv") else pd.read_excel(file)
            all_dfs.append(temp_df)
        
        raw_df = pd.concat(all_dfs, ignore_index=True)

        # 2. Run Predictions
        with st.spinner("Analyzing Batch Data..."):
            results = predict_future_faults(raw_df)

        if not results:
            st.warning("No significant future fault risk detected.")
            st.stop()

        results_df = pd.DataFrame(results)

        # 3. Automation: Auto-send emails immediately after prediction
        if "emails_sent" not in st.session_state:
            with st.spinner("Automating Email Dispatches..."):
                count = auto_dispatch_emails(results_df)
                st.session_state["emails_sent"] = True
                st.sidebar.success(f"✅ Automated alerts sent to {count} teams!")

        # 4. KPI METRIC CARDS
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total Predictions", len(results_df))
        col2.metric("Critical Risks (High)", len(results_df[results_df["Risk Level"] == "HIGH"]))
        col3.metric("Affected Sites", results_df["Site"].nunique())
        col4.metric("Avg. Probability", f"{round(results_df['Probability (%)'].mean(), 1)}%")

        st.markdown("---")

        # 5. VISUAL ANALYTICS (INDENTED CORRECTLY)
        st.markdown("### 📈 Analytical Deep-Dive")
        
        v_col1, v_col2 = st.columns([2, 1])
        with v_col1:
            st.subheader("📊 Fault Risk Probability Trend")
            chart = alt.Chart(results_df).mark_bar().encode(
                x=alt.X("Fault:N", sort="-y", title="Predicted Fault Type"),
                y=alt.Y("Probability (%):Q", title="Probability"),
                color=alt.Color("Risk Level:N", scale=alt.Scale(domain=["LOW", "MEDIUM", "HIGH"], range=["#2ecc71", "#f1c40f", "#e74c3c"])),
                tooltip=list(results_df.columns)
            ).properties(height=350)
            st.altair_chart(chart, use_container_width=True)

        with v_col2:
            st.subheader("🧮 Department Load")
            team_pie = alt.Chart(results_df).mark_arc().encode(
                theta="count()",
                color="Team:N",
                tooltip=["Team", "count()"]
            ).properties(height=350)
            st.altair_chart(team_pie, use_container_width=True)

        # Row 2: Site-wise Fault Count & Risk Distribution
        v_col3, v_col4 = st.columns(2)
        with v_col3:
            st.subheader("📍 Site-wise Fault Distribution")
            site_chart = alt.Chart(results_df).mark_bar().encode(
                y=alt.Y("Site:N", sort="-x", title="Site ID"),
                x=alt.X("count():Q", title="Number of Predicted Faults"),
                color=alt.Color("Fault:N", legend=alt.Legend(title="Fault Type")),
                tooltip=["Site", "Fault", "count()"]
            ).properties(height=400)
            st.altair_chart(site_chart, use_container_width=True)

        with v_col4:
            st.subheader("⚖️ Risk Level Volume")
            risk_vol = alt.Chart(results_df).mark_bar().encode(
                x=alt.X("Risk Level:N", sort=["HIGH", "MEDIUM", "LOW"]),
                y=alt.Y("count():Q", title="Total Alarms"),
                color=alt.Color("Risk Level:N", scale=alt.Scale(domain=["LOW", "MEDIUM", "HIGH"], range=["#2ecc71", "#f1c40f", "#e74c3c"])),
                tooltip=["Risk Level", "count()"]
            ).properties(height=400)
            st.altair_chart(risk_vol, use_container_width=True)

        # 6. DATA VIEW
        st.subheader("📋 Intelligence Report")
        st.dataframe(results_df, use_container_width=True)

        # 7. MANUAL EXPORT
        st.download_button("📥 Export NOC Master Report (CSV)", results_df.to_csv(index=False), "NOC_Report.csv", "text/csv")

    except Exception as e:
        st.error(f"Critical System Error: {e}")
else:
    if "emails_sent" in st.session_state:
        del st.session_state["emails_sent"]
    st.info("👈 Dashboard Idle. Please upload alarm logs in the sidebar to begin.")




