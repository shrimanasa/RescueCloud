from __future__ import annotations

import json
from datetime import datetime, timedelta
from urllib.request import Request, urlopen


API_URL = "http://127.0.0.1:8001/anomaly/predict"


def predict(event: dict) -> dict:
    request = Request(
        API_URL,
        data=json.dumps(event).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


detected_at = datetime.now().astimezone().replace(microsecond=0)
start_time = detected_at - timedelta(minutes=5)

events = [
    {
        "event_time": start_time,
        "payload": {
            "role": "doctor",
            "action": "view_record",
            "status": "success",
            "failed_logins": 0,
            "requests_per_minute": 10,
            "records_accessed": 4,
            "records_modified": 0,
            "records_deleted": 0,
            "export_size_mb": 0,
            "session_duration_min": 18,
            "off_hours_access": 0,
            "new_ip_address": 0,
            "privilege_change": 0,
        },
    },
    {
        "event_time": start_time + timedelta(minutes=1),
        "payload": {
            "role": "nurse",
            "action": "update_record",
            "status": "success",
            "failed_logins": 0,
            "requests_per_minute": 14,
            "records_accessed": 6,
            "records_modified": 2,
            "records_deleted": 0,
            "export_size_mb": 0,
            "session_duration_min": 22,
            "off_hours_access": 0,
            "new_ip_address": 0,
            "privilege_change": 0,
        },
    },
    {
        "event_time": start_time + timedelta(minutes=2),
        "payload": {
            "role": "admin",
            "action": "export_data",
            "status": "success",
            "failed_logins": 1,
            "requests_per_minute": 35,
            "records_accessed": 120,
            "records_modified": 0,
            "records_deleted": 0,
            "export_size_mb": 25,
            "session_duration_min": 20,
            "off_hours_access": 0,
            "new_ip_address": 0,
            "privilege_change": 0,
        },
    },
    {
        "event_time": start_time + timedelta(minutes=3),
        "payload": {
            "role": "admin",
            "action": "export_data",
            "status": "success",
            "failed_logins": 6,
            "requests_per_minute": 110,
            "records_accessed": 1100,
            "records_modified": 0,
            "records_deleted": 0,
            "export_size_mb": 420,
            "session_duration_min": 17,
            "off_hours_access": 1,
            "new_ip_address": 1,
            "privilege_change": 0,
        },
    },
    {
        "event_time": start_time + timedelta(minutes=4),
        "payload": {
            "role": "admin",
            "action": "export_data",
            "status": "success",
            "failed_logins": 12,
            "requests_per_minute": 180,
            "records_accessed": 2500,
            "records_modified": 0,
            "records_deleted": 0,
            "export_size_mb": 950,
            "session_duration_min": 15,
            "off_hours_access": 1,
            "new_ip_address": 1,
            "privilege_change": 0,
        },
    },
]

results = []

print("Analysing audit-event timeline...\n")

for index, event in enumerate(events, start=1):
    result = predict(event["payload"])

    results.append(
        {
            "event_time": event["event_time"],
            "is_anomaly": result["is_anomaly"],
            "prediction": result["prediction"],
            "decision_score": result["decision_score"],
        }
    )

    print(
        f"Event {index}:",
        event["event_time"].isoformat(),
        "|",
        result["prediction"],
        "| score:",
        round(result["decision_score"], 5),
    )

anomalies = [
    result
    for result in results
    if result["is_anomaly"]
]

if not anomalies:
    raise RuntimeError(
        "No anomaly was detected in the event sequence."
    )

estimated_compromise_at = anomalies[0]["event_time"]

estimation_delay = (
    detected_at - estimated_compromise_at
).total_seconds()

print("\n========== COMPROMISE ESTIMATION ==========")
print("Estimated compromise time:", estimated_compromise_at.isoformat())
print("Detection time:", detected_at.isoformat())
print("Estimation delay:", estimation_delay, "seconds")
print("First anomalous score:", anomalies[0]["decision_score"])
print("===========================================")
