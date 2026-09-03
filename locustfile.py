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


class PharmacistUser(HttpUser):
    """
    Simulates a pharmacy staff member querying medication records.
    Lower frequency than clinical staff; occasionally exports prescription reports.
    """
    wait_time = between(2, 8)

    @tag('normal')
    @task(8)
    def view_medication_record(self):
        payload = {
            "role": "lab_technician",
            "action": "view_record",
            "status": "success",
            "failed_logins": 0,
            "requests_per_minute": random.randint(1, 6),
            "records_accessed": random.randint(1, 3),
            "records_modified": 0,
            "records_deleted": 0,
            "export_size_mb": 0.0,
            "session_duration_min": random.randint(5, 30),
            "off_hours_access": 0,
            "new_ip_address": 0,
            "privilege_change": 0,
        }
        self.client.post("/anomaly/predict", json=payload, name="Pharmacist Record View")

    @tag('normal')
    @task(2)
    def export_prescription_report(self):
        payload = {
            "role": "lab_technician",
            "action": "export_data",
            "status": "success",
            "failed_logins": 0,
            "requests_per_minute": random.randint(1, 3),
            "records_accessed": random.randint(10, 40),
            "records_modified": 0,
            "records_deleted": 0,
            "export_size_mb": round(random.uniform(0.5, 5.0), 2),
            "session_duration_min": random.randint(15, 45),
            "off_hours_access": 0,
            "new_ip_address": 0,
            "privilege_change": 0,
        }
        self.client.post("/anomaly/predict", json=payload, name="Pharmacist Report Export")


# export_size_mb set above 500 MB to reliably trigger the circuit breaker.
class MaliciousInsiderUser(HttpUser):
    """Slow-burn insider exfiltration above the 500 MB circuit-breaker threshold."""
    wait_time = between(30, 120)

    @tag('attack')
    @task(1)
    def slow_bulk_export(self):
        payload = {
            "role": "admin", "action": "export_data", "status": "success",
            "failed_logins": random.randint(0, 2),
            "requests_per_minute": random.randint(1, 4),
            "records_accessed": random.randint(800, 2000),
            "records_modified": 0, "records_deleted": 0,
            "export_size_mb": round(random.uniform(450.0, 950.0), 1),
            "session_duration_min": random.randint(60, 240),
            "off_hours_access": random.choice([0, 1]),
            "new_ip_address": 1, "privilege_change": random.choice([0, 1]),
        }
        self.client.post("/anomaly/predict", json=payload, name="Insider Slow Exfil")

# Note: MaliciousInsiderUser export_size_mb is above 500 MB
# to reliably trigger the circuit breaker in anomaly_detection_middleware.


# ---------------------------------------------------------------------------
# Running Locust
# ---------------------------------------------------------------------------
# Web UI mode (recommended for interactive testing):
#   locust -f locustfile.py --host=http://localhost:8001
#   Open http://localhost:8089
#
# Headless mode (for CI/automated load tests):
#   locust -f locustfile.py --host=http://localhost:8001 \\
#     --headless --users 50 --spawn-rate 5 --run-time 60s
#
# To include attack scenarios: add MaliciousInsiderUser to the --class-picker


# Locust metrics to watch during a load test:
#   - Request failure rate (should be 0% for normal users, 0% for anomaly trigger)
#   - Response time P95 (should be < 200ms for /anomaly/predict)
#   - Circuit breaker activation (check /anomaly/blast-radius during MaliciousInsiderUser run)
