from __future__ import annotations

import csv
import random
from datetime import datetime, timedelta
from pathlib import Path


SEED = 42
NORMAL_ROWS = 47_500
ANOMALY_ROWS = 2_500

random.seed(SEED)

PROJECT_DIR = Path(__file__).resolve().parents[1]
PATIENTS_FILE = PROJECT_DIR / "data/synthea/csv/patients.csv"
OUTPUT_FILE = (
    PROJECT_DIR
    / "data/activity_logs/rescuecloud_audit_logs.csv"
)

USERS = {
    "doctor": [f"doctor_{i:03d}" for i in range(1, 81)],
    "nurse": [f"nurse_{i:03d}" for i in range(1, 101)],
    "admin": [f"admin_{i:03d}" for i in range(1, 16)],
    "lab_technician": [f"lab_{i:03d}" for i in range(1, 31)],
    "receptionist": [f"reception_{i:03d}" for i in range(1, 31)],
}

ROLE_ACTIONS = {
    "doctor": [
        "login",
        "view_record",
        "update_record",
        "export_data",
    ],
    "nurse": [
        "login",
        "view_record",
        "update_record",
    ],
    "admin": [
        "login",
        "view_record",
        "export_data",
        "delete_record",
        "privilege_change",
    ],
    "lab_technician": [
        "login",
        "view_record",
        "update_record",
    ],
    "receptionist": [
        "login",
        "view_record",
        "update_record",
    ],
}

FIELDNAMES = [
    "event_id",
    "timestamp",
    "user_id",
    "role",
    "action",
    "patient_id",
    "source_ip",
    "failed_logins",
    "requests_per_minute",
    "records_accessed",
    "records_modified",
    "records_deleted",
    "export_size_mb",
    "session_duration_min",
    "off_hours_access",
    "new_ip_address",
    "privilege_change",
    "status",
    "label",
    "anomaly_type",
]


def load_patient_ids() -> list[str]:
    if not PATIENTS_FILE.exists():
        raise FileNotFoundError(
            f"Patient dataset not found: {PATIENTS_FILE}"
        )

    with PATIENTS_FILE.open(
        newline="",
        encoding="utf-8",
    ) as file:
        return [
            row["Id"]
            for row in csv.DictReader(file)
            if row.get("Id")
        ]


PATIENT_IDS = load_patient_ids()
START_DATE = datetime(2026, 6, 1)


def create_timestamp(off_hours: int) -> str:
    day_offset = random.randint(0, 29)

    if off_hours:
        hour = random.choice([0, 1, 2, 3, 4, 5, 22, 23])
    else:
        hour = random.randint(7, 20)

    value = START_DATE + timedelta(
        days=day_offset,
        hours=hour,
        minutes=random.randint(0, 59),
        seconds=random.randint(0, 59),
    )

    return value.isoformat()


def internal_ip() -> str:
    return (
        f"10.0.{random.randint(1, 20)}."
        f"{random.randint(2, 254)}"
    )


def external_ip() -> str:
    prefix = random.choice(["198.51.100", "203.0.113"])
    return f"{prefix}.{random.randint(2, 254)}"


def create_normal_row() -> dict:
    role = random.choices(
        list(USERS),
        weights=[35, 35, 8, 10, 12],
        k=1,
    )[0]

    user_id = random.choice(USERS[role])
    action = random.choice(ROLE_ACTIONS[role])

    off_hours = int(random.random() < 0.03)
    new_ip = int(random.random() < 0.01)

    failed_logins = 0
    status = "success"

    if action == "login" and random.random() < 0.04:
        failed_logins = random.randint(1, 2)
        status = "failed"

    records_accessed = 0
    records_modified = 0
    records_deleted = 0
    export_size_mb = 0.0

    if action == "view_record":
        records_accessed = random.randint(1, 15)

    elif action == "update_record":
        records_accessed = random.randint(1, 6)
        records_modified = random.randint(1, 4)

    elif action == "export_data":
        records_accessed = random.randint(5, 50)
        export_size_mb = round(random.uniform(0.2, 8.0), 2)

    elif action == "delete_record":
        records_accessed = random.randint(1, 5)
        records_deleted = random.randint(1, 2)

    privilege_change = int(
        role == "admin" and action == "privilege_change"
    )

    return {
        "event_id": "",
        "timestamp": create_timestamp(off_hours),
        "user_id": user_id,
        "role": role,
        "action": action,
        "patient_id": (
            ""
            if action == "login"
            else random.choice(PATIENT_IDS)
        ),
        "source_ip": external_ip() if new_ip else internal_ip(),
        "failed_logins": failed_logins,
        "requests_per_minute": random.randint(1, 20),
        "records_accessed": records_accessed,
        "records_modified": records_modified,
        "records_deleted": records_deleted,
        "export_size_mb": export_size_mb,
        "session_duration_min": random.randint(2, 180),
        "off_hours_access": off_hours,
        "new_ip_address": new_ip,
        "privilege_change": privilege_change,
        "status": status,
        "label": 0,
        "anomaly_type": "normal",
    }


def create_anomaly_row() -> dict:
    row = create_normal_row()

    anomaly_type = random.choice(
        [
            "brute_force_login",
            "mass_data_export",
            "bulk_record_deletion",
            "privilege_escalation",
            "high_frequency_access",
            "unusual_off_hours_access",
        ]
    )

    row["label"] = 1
    row["anomaly_type"] = anomaly_type

    if anomaly_type == "brute_force_login":
        row["action"] = "login"
        row["patient_id"] = ""
        row["failed_logins"] = random.randint(8, 30)
        row["requests_per_minute"] = random.randint(30, 150)
        row["new_ip_address"] = 1
        row["source_ip"] = external_ip()
        row["status"] = "failed"

    elif anomaly_type == "mass_data_export":
        row["action"] = "export_data"
        row["records_accessed"] = random.randint(500, 5000)
        row["export_size_mb"] = round(
            random.uniform(100, 2000),
            2,
        )
        row["requests_per_minute"] = random.randint(50, 300)
        row["off_hours_access"] = 1
        row["new_ip_address"] = 1
        row["source_ip"] = external_ip()

    elif anomaly_type == "bulk_record_deletion":
        row["action"] = "delete_record"
        row["records_accessed"] = random.randint(100, 1500)
        row["records_deleted"] = random.randint(50, 1000)
        row["requests_per_minute"] = random.randint(30, 200)
        row["off_hours_access"] = 1

    elif anomaly_type == "privilege_escalation":
        row["role"] = random.choice(
            ["doctor", "nurse", "lab_technician", "receptionist"]
        )
        row["user_id"] = random.choice(USERS[row["role"]])
        row["action"] = "privilege_change"
        row["privilege_change"] = 1
        row["new_ip_address"] = 1
        row["source_ip"] = external_ip()

    elif anomaly_type == "high_frequency_access":
        row["action"] = "view_record"
        row["records_accessed"] = random.randint(200, 2000)
        row["requests_per_minute"] = random.randint(100, 500)

    elif anomaly_type == "unusual_off_hours_access":
        row["off_hours_access"] = 1
        row["new_ip_address"] = 1
        row["source_ip"] = external_ip()
        row["records_accessed"] = random.randint(100, 800)
        row["requests_per_minute"] = random.randint(30, 150)

    row["timestamp"] = create_timestamp(
        int(row["off_hours_access"])
    )

    return row


rows = [
    create_normal_row()
    for _ in range(NORMAL_ROWS)
]

rows.extend(
    create_anomaly_row()
    for _ in range(ANOMALY_ROWS)
)

rows.sort(key=lambda row: row["timestamp"])

for index, row in enumerate(rows, start=1):
    row["event_id"] = f"event_{index:06d}"

OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

with OUTPUT_FILE.open(
    "w",
    newline="",
    encoding="utf-8",
) as file:
    writer = csv.DictWriter(file, fieldnames=FIELDNAMES)
    writer.writeheader()
    writer.writerows(rows)

print(f"Dataset created: {OUTPUT_FILE}")
print(f"Total records: {len(rows)}")
print(f"Normal records: {NORMAL_ROWS}")
print(f"Anomaly records: {ANOMALY_ROWS}")
