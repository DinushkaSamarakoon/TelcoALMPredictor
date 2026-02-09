import pandas as pd
import joblib
from pathlib import Path
from collections import defaultdict

from sklearn.preprocessing import MultiLabelBinarizer
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, hamming_loss

# ============================================================
# CONFIGURATION
# ============================================================

DATA_DIR = Path("data")
MODEL_DIR = Path("model")

TIME_WINDOW_MINUTES = 10
HISTORY_WINDOWS = 3

MODEL_DIR.mkdir(exist_ok=True)

# ============================================================
# FAULT → CAUSE → RECOMMENDATION → TEAM
# ============================================================

FAULT_DATA = {
    "gsm_local_cell_unusable": {
        "cause": "TRX failure, RF link down, power issue",
        "recommendation": "Verify RF unit status, reset TRX, check DC input and feeders",
        "team": "Field"
    },
    "bbu_cpri_interface_error": {
        "cause": "Fiber link loss, dirty connector, CPRI port failure",
        "recommendation": "Clean fiber connectors, check SFP power, replace fiber or CPRI port",
        "team": "Field + NOC"
    },
    "rf_unit_tx_channel_gain_out_of_range": {
        "cause": "PA degradation, temperature impact, calibration error",
        "recommendation": "Check RF unit temperature, recalibrate RF path, replace RFU if persistent",
        "team": "Field"
    },
    "tbc_battery_cabinet_high_temperature": {
        "cause": "Poor ventilation or fan failure",
        "recommendation": "Improve ventilation, check fans, reduce load if needed",
        "team": "Field"
    },
    "cell_capability_degraded": {
        "cause": "License limit exceeded or RF degradation",
        "recommendation": "Verify capacity license and RF configuration",
        "team": "NOC"
    },
    "capacity_license_issue": {
        "cause": "Configured or data capacity exceeding licensed limit",
        "recommendation": "Verify license and apply capacity upgrade",
        "team": "NOC"
    },
    "rf_unit_clock_problem": {
        "cause": "GNSS sync loss or clock module fault",
        "recommendation": "Check GNSS lock, inspect clock cable, switch to backup sync",
        "team": "NOC"
    },
    "ac_surge_protection_fault": {
        "cause": "Surge event or SPD degradation",
        "recommendation": "Replace surge protector and inspect grounding",
        "team": "Field"
    },
    "qos": {
        "cause": "High VSWR due to feeder or antenna fault",
        "recommendation": "Inspect feeders, tighten connectors, test antenna VSWR",
        "team": "Field"
    },
    # "ne_disconnected": {
    #     "cause": "Board startup failure, hardware fault, optical interface error",
    #     "recommendation": "Inspect boards and optical interfaces, replace faulty hardware",
    #     "team": "NOC"
    # },
    "battery_discharging": {
        "cause": "AC failure, rectifier fault, power fluctuation",
        "recommendation": "Check AC input, rectifiers, breakers, and battery health",
        "team": "Field"
    },
    "indoor_vent_high_temperature": {
        "cause": "Fan fault or blocked ventilation",
        "recommendation": "Replace faulty fans and clear airflow paths",
        "team": "Field"
    },
    "power_monitoring_failure": {
        "cause": "Power module and monitoring module communication failure",
        "recommendation": "Check power monitoring module connections and reboot module",
        "team": "Field"
    },
    "battery_health_issue": {
        "cause": "Battery protection triggered or over-discharge",
        "recommendation": "Perform battery health check and replace battery if required",
        "team": "Field"
    },
    "no_fault": {
        "cause": "No abnormal condition detected",
        "recommendation": "Continue monitoring",
        "team": "NOC"
    }
}

# ============================================================
# LOAD ALARM FILES
# ============================================================

def load_alarm_files(data_dir):
    dfs = []

    for file in data_dir.iterdir():
        if file.suffix.lower() not in [".csv", ".xlsx"]:
            continue

        try:
            print(f"Loading {file}")

            if file.suffix.lower() == ".csv":
                df = pd.read_csv(file, engine="python", sep=None, on_bad_lines="skip")
            else:
                df = pd.read_excel(file)

            df.columns = (
                df.columns.astype(str)
                .str.strip()
                .str.lower()
                .str.replace(" ", "_")
            )

            df = df.rename(columns={
                "site_name": "ne_name",
                "last_occurred": "raised_on"
            })

            required = {"raised_on", "ne_name", "name", "location_info"}
            if not required.issubset(df.columns):
                raise ValueError(f"Missing columns: {required - set(df.columns)}")

            df["raised_on"] = pd.to_datetime(df["raised_on"], errors="coerce")
            dfs.append(df[list(required)])

        except Exception as e:
            print(f"Skipping {file}: {e}")

    if not dfs:
        raise RuntimeError("No valid alarm files found")

    return pd.concat(dfs, ignore_index=True)


df = load_alarm_files(DATA_DIR)

# ============================================================
# CLEAN ALARM NAMES
# ============================================================

df["alarm_clean"] = (
    df["name"]
    .astype(str)
    .str.lower()
    .str.replace(r"[^a-z0-9 ]", "", regex=True)
    .str.replace(" ", "_")
)

# ============================================================
# LOCATION KEY
# ============================================================

def build_location_key(loc):
    loc = str(loc).lower()
    cabinet = subrack = slot = "?"
    for p in loc.split(","):
        if "cabinet" in p:
            cabinet = p.strip()
        elif "subrack" in p:
            subrack = p.strip()
        elif "slot" in p:
            slot = p.strip()
    return f"{cabinet}|{subrack}|{slot}"

df["location_key"] = df["location_info"].apply(build_location_key)

# ============================================================
# TIME WINDOW
# ============================================================

df["time_window"] = df["raised_on"].dt.floor(f"{TIME_WINDOW_MINUTES}min")

# ============================================================
# GROUP ALARMS
# ============================================================

alarm_groups = []
alarm_meta = []

for (ne, loc, win), g in df.groupby(["ne_name", "location_key", "time_window"]):
    alarm_groups.append(g["alarm_clean"].tolist())
    alarm_meta.append((ne, loc, win))

# ============================================================
# RULE-BASED FAULT LABELING (MATCHES YOUR CHART)
# ============================================================

fault_labels = []

for alarms in alarm_groups:
    s = set(alarms)
    faults = []

    if {
        "rf_unit_dc_input_power_failure",
        "rf_unit_runtime_topology_error",
        "cell_unavailable",
        "rf_unit_maintenance_link_failure",
        "remote_maintenance_link_failure"
    } & s:
        faults.append("gsm_local_cell_unusable")

    if {"bbu_cpri_interface_error"} & s:
        faults.append("bbu_cpri_interface_error")

    if {"rf_unit_tx_channel_gain_out_of_range"} & s:
        faults.append("rf_unit_tx_channel_gain_out_of_range")

    if {"tbc_battery_cabinet_high_temperature"} & s:
        faults.append("tbc_battery_cabinet_high_temperature")

    if {"cell_capability_degraded"} & s:
        faults.append("cell_capability_degraded")

    if {
        "configured_capacity_limit_exceeding_licensed_limit",
        "data_configuration_exceeding_licensed_limit"
    } & s:
        faults.append("capacity_license_issue")

    if {"rf_unit_clock_problem"} & s:
        faults.append("rf_unit_clock_problem")

    if {"ac_surge_protector_fault"} & s:
        faults.append("ac_surge_protection_fault")

    if {"rf_unit_vswr_threshold_crossed"} & s:
        faults.append("qos")

    # if {
    #     "board_startup",
    #     "board_hardware_fault",
    #     "transmission_optical_interface_error"
    # } & s:
    #     faults.append("ne_disconnected")

    if {
        "mains_input_out_of_range",
        "mains_failure",
        "ac_failure",
        "phase_l1_under_voltage",
        "phase_l2_under_voltage",
        "phase_l3_under_voltage"
    } & s:
        faults.append("battery_discharging")

    if {"fan_1_fault", "fan_2_fault", "fan_3_fault", "fan_4_fault"} & s:
        faults.append("indoor_vent_high_temperature")

    if {"power_module_and_monitoring_module_communication_failure"} & s:
        faults.append("power_monitoring_failure")

    if {"lithium_battery_protection", "overdischarge"} & s:
        faults.append("battery_health_issue")

    if not faults:
        faults.append("no_fault")

    fault_labels.append(faults)

# ============================================================
# BUILD TEMPORAL DATASET
# ============================================================

timeline = defaultdict(list)

for alarms, meta, faults in zip(alarm_groups, alarm_meta, fault_labels):
    ne, loc, win = meta
    timeline[(ne, loc)].append((win, alarms, faults))

X_seq, y_seq = [], []

for records in timeline.values():
    records.sort(key=lambda x: x[0])

    for i in range(HISTORY_WINDOWS, len(records)):
        past = []
        for j in range(i - HISTORY_WINDOWS, i):
            past.extend(records[j][1])

        X_seq.append(past)
        y_seq.append(records[i][2])

# ============================================================
# ENCODING
# ============================================================

alarm_encoder = MultiLabelBinarizer()
fault_encoder = MultiLabelBinarizer()

X = alarm_encoder.fit_transform(X_seq)
y = fault_encoder.fit_transform(y_seq)

# ============================================================
# TRAIN MODEL
# ============================================================

X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42
)

model = RandomForestClassifier(
    n_estimators=300,
    class_weight="balanced",
    random_state=42,
    n_jobs=-1
)

model.fit(X_train, y_train)

# ============================================================
# EVALUATION
# ============================================================

y_pred = model.predict(X_test)

print("\n--- MODEL EVALUATION ---\n")
print(classification_report(
    y_test,
    y_pred,
    target_names=fault_encoder.classes_,
    zero_division=0
))
print("Hamming Loss:", hamming_loss(y_test, y_pred))

# ============================================================
# SAVE EVERYTHING
# ============================================================

joblib.dump(model, MODEL_DIR / "future_fault_model.pkl")
joblib.dump(alarm_encoder, MODEL_DIR / "alarm_encoder.pkl")
joblib.dump(fault_encoder, MODEL_DIR / "fault_encoder.pkl")
joblib.dump(FAULT_DATA, MODEL_DIR / "FAULT_DATA.pkl")

print("\nTraining completed successfully.")
print("Model, encoders, and FAULT_DATA saved.")
