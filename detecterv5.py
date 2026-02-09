import pandas as pd
import joblib
from collections import defaultdict
from pathlib import Path
import re

# =====================================================
# CONFIGURATION
# =====================================================

MODEL_DIR = "model"

MODEL_PATH = Path(MODEL_DIR) / "future_fault_model.pkl"
ALARM_ENCODER_PATH = Path(MODEL_DIR) / "alarm_encoder.pkl"
FAULT_ENCODER_PATH = Path(MODEL_DIR) / "fault_encoder.pkl"
FAULT_DATA_PATH = Path(MODEL_DIR) / "FAULT_DATA.pkl"

TIME_WINDOW_MINUTES = 10
HISTORY_WINDOWS = 3
MIN_RISK = 0.01

DATETIME_REGEX = r"\d{4}-\d{2}-\d{2}[_ ]\d{2}:\d{2}:\d{2}"

# =====================================================
# LOAD MODEL & METADATA
# =====================================================

model = joblib.load(MODEL_PATH)
alarm_encoder = joblib.load(ALARM_ENCODER_PATH)
fault_encoder = joblib.load(FAULT_ENCODER_PATH)
FAULT_DATA = joblib.load(FAULT_DATA_PATH)

# =====================================================
# FIX HORIZONTAL RECORD (DATA IN HEADERS)
# =====================================================

def fix_horizontal_alarm(df):
    if any(
        isinstance(c, str) and re.fullmatch(DATETIME_REGEX, c)
        for c in df.columns
    ):
        values = list(df.columns)
        df = pd.DataFrame([values])
        df.columns = [
            "severity",
            "name",
            "ne_name",
            "device",
            "manage_domain",
            "device_type",
            "location_info",
            "raised_on",
            "cleared_on"
        ][:len(values)]
    return df

# =====================================================
# NORMALIZE DATETIME (KEY FIX)
# =====================================================

def normalize_datetime(df):
    datetime_candidates = [
        "raised_on",
        "last_occurred",
        "occurred",
        "event_time",
        "alarm_time",
        "time"
    ]

    for col in df.columns:
        if col in datetime_candidates:
            df["raised_on"] = pd.to_datetime(
                df[col].astype(str).str.replace("_", " "),
                errors="coerce"
            )
            return df

    raise KeyError(
        f"No datetime column found. Available columns: {list(df.columns)}"
    )

# =====================================================
# LOCATION KEY
# =====================================================

def build_location_key(text):
    t = str(text).lower()
    cabinet = subrack = slot = "?"

    for part in t.split(","):
        if "cabinet" in part:
            cabinet = part.strip()
        elif "subrack" in part:
            subrack = part.strip()
        elif "slot" in part:
            slot = part.strip()

    return f"{cabinet}|{subrack}|{slot}"

# =====================================================
# CORE PREDICTION FUNCTION
# =====================================================

def predict_future_faults(raw_df):

    # Handle horizontal alarm format
    df = fix_horizontal_alarm(raw_df)

    # Normalize column names
    df.columns = (
        df.columns.astype(str)
        .str.strip()
        .str.lower()
        .str.replace(" ", "_")
    )

    # Normalize datetime
    df = normalize_datetime(df)

    # Normalize NE name
    df = df.rename(columns={
        "site_name": "ne_name"
    })

    required = {"raised_on", "ne_name", "name", "location_info"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    # Clean alarm names
    df["alarm_clean"] = (
        df["name"]
        .astype(str)
        .str.lower()
        .str.replace(r"[^a-z0-9 ]", "", regex=True)
        .str.replace(" ", "_")
    )

    # Build location key
    df["location_key"] = df["location_info"].apply(build_location_key)

    # Time windows
    df["time_window"] = df["raised_on"].dt.floor(
        f"{TIME_WINDOW_MINUTES}min"
    )

    # Build timeline
    timeline = defaultdict(list)
    for (ne, loc, win), g in df.groupby(
        ["ne_name", "location_key", "time_window"]
    ):
        timeline[(ne, loc)].append(
            (win, g["alarm_clean"].tolist())
        )

    results = []

    for (ne, loc), records in timeline.items():
        if len(records) < HISTORY_WINDOWS:
            continue

        recent = []
        for _, alarms in records[-HISTORY_WINDOWS:]:
            recent.extend(alarms)

        if not recent:
            continue

        X = alarm_encoder.transform([recent])
        probas = model.predict_proba(X)

        for i, fault in enumerate(fault_encoder.classes_):
            if fault == "no_fault":
                continue

            risk = probas[i][0][1]
            if risk < MIN_RISK:
                continue

            meta = FAULT_DATA.get(
                fault,
                {"cause": "Unknown", "recommendation": "N/A", "team": "N/A"}
            )

            results.append({
                "Site": ne,
                "Location": loc,
                "Fault": fault,
                "Probability (%)": round(risk * 100, 4),
                "Risk Level": (
                    "HIGH" if risk >= 0.5
                    else "MEDIUM" if risk >= 0.25
                    else "LOW"
                ),
                "Possible Cause": meta["cause"],
                "Recommendation": meta["recommendation"],
                "Team": meta["team"]
            })

    return results
