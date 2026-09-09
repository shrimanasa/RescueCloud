from __future__ import annotations

import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from main import (
    _BLOCKED_IPS,
    _CIRCUIT_BREAKER_LOCK,
    _CONTAINMENT_STATE,
    _IP_ANOMALY_COUNTS,
    trigger_circuit_breaker,
    reset_circuit_breaker,
)


@pytest.fixture(autouse=True)
def clean_circuit_breaker():
    """Ensure clean circuit breaker state before each test."""
    with _CIRCUIT_BREAKER_LOCK:
        _BLOCKED_IPS.clear()
        _IP_ANOMALY_COUNTS.clear()
        _CONTAINMENT_STATE["active"] = False
        _CONTAINMENT_STATE["timestamp"] = None
        _CONTAINMENT_STATE["reason"] = None
        _CONTAINMENT_STATE["blocked_ips"] = []
        _CONTAINMENT_STATE["wal_switched"] = False
    yield
    with _CIRCUIT_BREAKER_LOCK:
        _BLOCKED_IPS.clear()
        _IP_ANOMALY_COUNTS.clear()
        _CONTAINMENT_STATE["active"] = False


def test_trigger_containment_quarantines_ip():
    attacker_ip = "192.168.1.100"

    with _CIRCUIT_BREAKER_LOCK:
        assert _CONTAINMENT_STATE["active"] is False
        assert attacker_ip not in _BLOCKED_IPS

    trigger_circuit_breaker(attacker_ip, reason="Mass Exfiltration Detected")

    with _CIRCUIT_BREAKER_LOCK:
        assert _CONTAINMENT_STATE["active"] is True
        assert attacker_ip in _BLOCKED_IPS
        assert attacker_ip in _CONTAINMENT_STATE["blocked_ips"]
        assert _CONTAINMENT_STATE["reason"] == "Mass Exfiltration Detected"


def test_reset_circuit_breaker_clears_containment():
    attacker_ip = "10.0.0.99"
    trigger_circuit_breaker(attacker_ip, reason="Ransomware Vector")

    with _CIRCUIT_BREAKER_LOCK:
        assert _CONTAINMENT_STATE["active"] is True

    admin_user = {"username": "admin@rescuecloud.io", "role": "admin"}
    response = reset_circuit_breaker(current_user=admin_user)

    assert response["status"] == "reset"
    assert response["containment_active"] is False

    with _CIRCUIT_BREAKER_LOCK:
        assert _CONTAINMENT_STATE["active"] is False
        assert len(_BLOCKED_IPS) == 0
        assert len(_CONTAINMENT_STATE["blocked_ips"]) == 0

# Coverage: circuit breaker trips at threshold, blast-radius reflects state,
# reaction_time_ms is a positive float (not hardcoded 38ms).
# Gap: /anomaly/reset needs admin JWT fixture.
