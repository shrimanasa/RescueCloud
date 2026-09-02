"""
RescueCloud — Locust Traffic & Ransomware Load Simulator

Use Locust to simulate real-time concurrent hospital user traffic (Doctors & Nurses)
alongside sudden malicious ransomware data exfiltration spikes against the Isolation Forest API.

Usage:
  pip install locust
  locust -f locustfile.py --host=http://localhost:8001
"""

import random
from locust import HttpUser, task, between, tag

class HospitalStaffUser(HttpUser):
    """
    Simulates normal baseline hospital EHR activity.
    Doctors and nurses browsing patient records during work hours.
    """
    wait_time = between(1, 4)

    @tag('normal')
    @task(10)
    def view_patient_record(self):
        payload = {
            "role": random.choice(["doctor", "nurse"]),
            "action": "view_patient",
            "status": "success",
            "failed_logins": 0,
            "requests_per_minute": random.randint(2, 10),
            "records_accessed": random.randint(1, 5),
            "records_modified": 0,
            "records_deleted": 0,
            "export_size_mb": 0.0,
            "session_duration_min": random.randint(10, 60),
            "off_hours_access": 0,
            "new_ip_address": 0,
            "privilege_change": 0
        }
        self.client.post("/anomaly/predict", json=payload, name="Normal Doctor Access")


class RansomwareAttackerUser(HttpUser):
    """
    Simulates a high-velocity malicious ransomware attack bot.
    Fires rapid bulk export requests, off-hours access, and high failure rates.
    """
    wait_time = between(0.1, 0.5)

    @tag('attack')
    @task
    def execute_bulk_exfiltration(self):
        payload = {
            "role": "unauthorized",
            "action": "bulk_export",
            "status": "failed",
            "failed_logins": random.randint(10, 30),
            "requests_per_minute": random.randint(250, 600),
            "records_accessed": random.randint(2000, 10000),
            "records_modified": random.randint(50, 300),
            "records_deleted": random.randint(20, 150),
            "export_size_mb": round(random.uniform(400.0, 1500.0), 2),
            "session_duration_min": random.randint(1, 4),
            "off_hours_access": 1,
            "new_ip_address": 1,
            "privilege_change": 1
        }
        self.client.post("/anomaly/predict", json=payload, name="Ransomware Exfiltration Attack")
