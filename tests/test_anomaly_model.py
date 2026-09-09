from __future__ import annotations

import sys
from pathlib import Path

import joblib
import pandas as pd
import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
MODEL_PATH = BACKEND_DIR / "models" / "isolation_forest.joblib"


@pytest.fixture(scope="module")
def model():
    if not MODEL_PATH.exists():
        pytest.skip(f"Trained model not found at {MODEL_PATH}")
    return joblib.load(MODEL_PATH)


def test_model_loads_successfully(model):
    assert model is not None
    assert hasattr(model, "predict")
    assert hasattr(model, "decision_function")


def test_normal_traffic_not_flagged(model):
    """Normal clinical practitioner: routine doctor read event."""
    normal_sample = pd.DataFrame([{
        "role": "doctor",
        "action": "view_patient",
        "status": "success",
        "failed_logins": 0,
        "requests_per_minute": 12,
        "records_accessed": 2,
        "records_modified": 0,
        "records_deleted": 0,
        "export_size_mb": 0.0,
        "session_duration_min": 15,
        "off_hours_access": 0,
        "new_ip_address": 0,
        "privilege_change": 0,
    }])

    pred = model.predict(normal_sample)
    score = float(model.decision_function(normal_sample)[0])

    assert pred[0] == 1, f"Expected inlier (1), got {pred[0]} with score {score}"


def test_exfiltration_attack_flagged_as_anomaly(model):
    """Malicious exfiltration: mass export, high RPM, off hours from new IP."""
    attack_sample = pd.DataFrame([{
        "role": "anonymous",
        "action": "bulk_export",
        "status": "failed",
        "failed_logins": 5,
        "requests_per_minute": 2500,
        "records_accessed": 4000,
        "records_modified": 500,
        "records_deleted": 200,
        "export_size_mb": 850.0,
        "session_duration_min": 1,
        "off_hours_access": 1,
        "new_ip_address": 1,
        "privilege_change": 1,
    }])

    pred = model.predict(attack_sample)
    score = float(model.decision_function(attack_sample)[0])

    assert pred[0] == -1, f"Expected outlier anomaly (-1), got {pred[0]} with score {score}"

# Coverage: normal events, exfiltration, mass deletion, off-hours access.
# Gap: exactly-at-threshold events; missing feature columns.
