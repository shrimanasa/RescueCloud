"""
health_check.py -- RescueCloud Service Health Checker
======================================================
Polls all RescueCloud service endpoints and reports their health status.
Useful for pre-deployment validation and ongoing monitoring.

Usage:
  python3 scripts/health_check.py
  python3 scripts/health_check.py --host http://localhost:8001
"""
from __future__ import annotations

import argparse
import json
from urllib.error import URLError
from urllib.request import urlopen

DEFAULT_HOST = "http://localhost:8001"
TIMEOUT = 5


def check(url: str, name: str) -> bool:
    try:
        with urlopen(url, timeout=TIMEOUT) as resp:
            ok = 200 <= resp.status < 400
            status = resp.status
    except URLError as e:
        ok, status = False, str(e)
    except Exception as e:
        ok, status = False, str(e)

    symbol = "OK" if ok else "FAIL"
    print(f"  [{symbol}] {name}: {status}")
    return bool(ok)


def main(host: str) -> None:
    print(f"RescueCloud Health Check — {host}\n")
    results = [
        check(f"{host}/health", "API /health"),
        check(f"{host}/metrics", "Prometheus /metrics"),
    ]
    total = len(results)
    passed = sum(results)
    print(f"\n{passed}/{total} checks passed.")
    if passed < total:
        raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=DEFAULT_HOST)
    args = parser.parse_args()
    main(args.host)


# ---------------------------------------------------------------------------
# Kubernetes liveness probe integration
# ---------------------------------------------------------------------------
# Add to your Deployment spec:
#   livenessProbe:
#     exec:
#       command: [python3, /app/scripts/health_check.py]
#     initialDelaySeconds: 30
#     periodSeconds: 30
#     failureThreshold: 3


# ---------------------------------------------------------------------------
# Extended checks
# ---------------------------------------------------------------------------
# To check Postgres connectivity:
#   psql $DATABASE_URL -c 'SELECT 1'
# To check Redis:
#   redis-cli -h $REDIS_HOST ping
# To check WAL archiving:
#   psql $DATABASE_URL -c 'SELECT pg_walfile_name(pg_current_wal_lsn())'
# Add these to the health_check script for a comprehensive pre-flight check.


# ---------------------------------------------------------------------------
# Health check response contract
# ---------------------------------------------------------------------------
# The /health endpoint (if implemented) should return:
#   HTTP 200 with body: {"status": "healthy", "version": "2.4.0"}
# A non-200 response or connection timeout indicates the service is unhealthy.
# Load balancers and Kubernetes probes use this to remove unhealthy pods.


# ---------------------------------------------------------------------------
# Alerting integration
# ---------------------------------------------------------------------------
# To send a PagerDuty alert when health check fails:
#   import requests
#   requests.post('https://events.pagerduty.com/v2/enqueue', json={
#     'routing_key': os.environ['PAGERDUTY_ROUTING_KEY'],
#     'event_action': 'trigger',
#     'payload': {'summary': 'RescueCloud health check failed', 'severity': 'critical'}
#   })


# ---------------------------------------------------------------------------
# Synthetic monitoring
# ---------------------------------------------------------------------------
# Run health_check.py from an external location every 5 minutes:
#   */5 * * * * python3 /path/to/scripts/health_check.py --host https://your-domain.com
# This provides outside-in monitoring that catches issues not visible
# from within the Kubernetes cluster (e.g. ingress or DNS failures).
