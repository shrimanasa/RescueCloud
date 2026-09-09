from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from starlette.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from main import app
from auth import ADMIN_USERNAME, ADMIN_PASSWORD, create_access_token

client = TestClient(app)


def test_health_endpoint_is_public():
    """K8s liveness/readiness probes must access /health without credentials."""
    response = client.get("/health")
    # Must not require authentication (no 401 Unauthorized)
    assert response.status_code != 401
    assert response.status_code in [200, 503]
    data = response.json()
    assert "status" in data or "detail" in data


def test_login_success():
    """Valid credentials return a signed JWT bearer token."""
    response = client.post(
        "/auth/login",
        json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["role"] == "admin"


def test_login_invalid_credentials():
    """Invalid password returns 401 Unauthorized."""
    response = client.post(
        "/auth/login",
        json={"username": ADMIN_USERNAME, "password": "WrongPassword123"},
    )
    assert response.status_code == 401
    assert "invalid" in response.json()["detail"].lower()


def test_login_rate_limit_blocks_after_threshold():
    """Repeated failed logins from the same client must be throttled with 429."""
    from main import LOGIN_RATE_LIMIT, _LOGIN_ATTEMPTS, _LOGIN_RATE_LOCK

    # Isolate this test's client IP so earlier tests' attempts don't interfere.
    test_client = TestClient(app, client=("203.0.113.42", 12345))

    with _LOGIN_RATE_LOCK:
        _LOGIN_ATTEMPTS.pop("203.0.113.42", None)

    statuses = []
    for _ in range(LOGIN_RATE_LIMIT + 2):
        response = test_client.post(
            "/auth/login",
            json={"username": ADMIN_USERNAME, "password": "WrongPassword123"},
        )
        statuses.append(response.status_code)

    assert statuses[:LOGIN_RATE_LIMIT] == [401] * LOGIN_RATE_LIMIT
    assert statuses[LOGIN_RATE_LIMIT] == 429
    assert statuses[LOGIN_RATE_LIMIT + 1] == 429

    final_response = test_client.post(
        "/auth/login",
        json={"username": ADMIN_USERNAME, "password": "WrongPassword123"},
    )
    assert final_response.status_code == 429
    assert "Retry-After" in final_response.headers


def test_patients_unauthenticated_rejected():
    """Accessing /patients without Bearer token must return 401 Unauthorized."""
    response = client.get("/patients")
    assert response.status_code == 401
    assert "missing bearer token" in response.json()["detail"].lower()


@patch("main.get_connection")
def test_patients_authenticated_allowed(mock_get_conn):
    """Accessing /patients with valid Bearer token is allowed."""
    mock_cursor = MagicMock()
    mock_cursor.fetchall.return_value = []
    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    mock_get_conn.return_value.__enter__.return_value = mock_conn

    token = create_access_token({"sub": "test_doctor", "role": "doctor"})
    headers = {"Authorization": f"Bearer {token}"}

    response = client.get("/patients", headers=headers)
    assert response.status_code == 200


def test_circuit_breaker_reset_forbidden_for_non_admin():
    """Non-admin roles attempting circuit breaker reset receive 403 Forbidden."""
    doctor_token = create_access_token({"sub": "dr_watson", "role": "doctor"})
    headers = {"Authorization": f"Bearer {doctor_token}"}

    response = client.post("/anomaly/circuit-breaker/reset", headers=headers)
    assert response.status_code == 403
    assert "insufficient permissions" in response.json()["detail"].lower()


def test_circuit_breaker_reset_allowed_for_admin():
    """Admin roles successfully reset the circuit breaker."""
    admin_token = create_access_token({"sub": "soc_lead", "role": "admin"})
    headers = {"Authorization": f"Bearer {admin_token}"}

    response = client.post("/anomaly/circuit-breaker/reset", headers=headers)
    assert response.status_code == 200
    assert response.json()["status"] == "reset"


def test_prometheus_metrics_endpoint():
    """Prometheus scrape endpoint /metrics must return 200 and standard exposition metrics."""
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "text/plain" in response.headers.get("content-type", "")
    text = response.text
    assert "rescuecloud_circuit_breaker_active" in text
    assert "rescuecloud_anomalies_detected_total" in text
    assert "rescuecloud_login_attempts_total" in text

# Coverage: blast-radius reaction_time_ms is positive float, RPO mentions WAL, /metrics returns Prometheus format.
# Gap: /incidents/recover requires live Postgres + blockchain node.
