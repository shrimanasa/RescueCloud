# RescueCloud Testing Guide

## Running Tests

```bash
# Full test suite
pytest --tb=short -q

# With coverage report
pytest --cov=backend --cov-report=term-missing

# Single test file
pytest tests/test_auth.py -v

# Single test function
pytest tests/test_circuit_breaker.py::test_circuit_breaker_trips -v
```

## Test Structure

| File | Coverage |
|---|---|
| `test_anomaly_model.py` | Isolation Forest scoring, feature schema |
| `test_api_endpoints.py` | FastAPI route responses, auth integration |
| `test_auth.py` | JWT issuance, RBAC, rate limiting |
| `test_circuit_breaker.py` | Containment state, blast-radius endpoint |
| `test_crypto_integrity.py` | SHA-256 backup hash verification |

## Test Environment

All tests use the `conftest.py` fixtures which inject fake env vars so
the backend can start without a real `.env` file. Tests run against
an in-process TestClient — no real database or blockchain required.

## Adding New Tests

1. Add a new `test_*.py` file under `tests/`.
2. Use the `client` fixture for API tests.
3. Mock external dependencies (Postgres, Redis, Web3) using `unittest.mock`.
4. Run `pytest` and confirm green before opening a PR.


## Performance Testing

Run the Locust load simulator to validate API performance under load:

```bash
# Start the API and load balancer
docker compose up -d

# Run 50 concurrent users for 60 seconds
locust -f locustfile.py --host=http://localhost:8001 \\
  --headless --users 50 --spawn-rate 10 --run-time 60s
```

**Acceptance criteria:**
- P95 response time for `/anomaly/predict` < 200ms
- Error rate < 0.1% for normal traffic
- Circuit breaker trips within 5s of MaliciousInsiderUser payload


## Test Coverage Targets

| Module | Current Coverage | Target |
|---|---|---|
| `backend/main.py` | ~70% | 85% |
| `backend/auth.py` | ~90% | 95% |
| `backend/incidents.py` | ~60% | 80% |
| `ml/train_isolation_forest.py` | 0% | 60% |
| `scripts/smart_recover.py` | 0% | 50% |

Run `pytest --cov=backend --cov-report=term-missing` to see current line coverage.


## Regression Testing After Model Retrain

After retraining `ml/models/isolation_forest.joblib`:

1. Run `pytest tests/test_anomaly_model.py -v` — all scoring tests must pass
2. Run `python3 ml/evaluate_model.py` — recall must be >= 0.90
3. Run `python3 ml/feature_importance.py` — verify expected feature ranking
4. Run the research experiment: `python3 scripts/run_research_experiment.py`
5. Compare results to `results/research_metrics.csv` baseline

If RTO or clean recovery rate regresses, do not merge the new model.


## Security Testing

Run these manual tests before any production deployment:

1. **Auth bypass**: access `/incidents` without a token → expect 401
2. **Role escalation**: access `/anomaly/reset` with non-admin token → expect 403
3. **Rate limit**: send 6 login requests in 60s from same IP → expect 429
4. **JWT tampering**: modify a valid token's payload and re-sign → expect 401
5. **SQL injection**: send `'; DROP TABLE patients; --` in any string field → expect 422
6. **CORS**: send request from unlisted origin → expect CORS headers absent


## Chaos Engineering

Periodically inject failures to validate resilience:

```bash
# Kill the primary Postgres pod (CloudNativePG should promote standby)
kubectl delete pod -n rescuecloud postgres-primary-0
kubectl get pods -n rescuecloud -w  # watch promotion

# Stop Redis (EventBus should fall back to in-process)
kubectl scale deployment redis --replicas=0 -n rescuecloud
# verify /anomaly/predict still responds
kubectl scale deployment redis --replicas=1 -n rescuecloud

# Run full ransomware simulation
python3 scripts/run_mock_attack.py
```


## Test Data Management

- Use `ml/generate_audit_logs.py` (SEED=42) for deterministic test data.
- Never use real patient data in tests — use Synthea-generated synthetic data.
- Clean up test artifacts after integration tests: `DROP TABLE security_incidents; CREATE TABLE ...`
- Use database transactions in tests and roll back after each test run.
- Store expected test outputs in `results/` (not hardcoded in test files).


## Mutation Testing

Consider running mutation testing with `mutmut` to validate test quality:

```bash
pip install mutmut
mutmut run --paths-to-mutate backend/
mutmut results
```

Focus mutation testing on:
- `backend/auth.py` — security-critical comparison operators
- `backend/main.py` — circuit breaker threshold logic
- `blockchain/verify_latest_backup.py` — hash comparison
High mutation score (>80%) indicates tests are catching logic errors.


## Definition of Done

A feature is considered complete when:

1. All unit tests pass (`pytest --tb=short -q`)
2. New code has test coverage for the happy path and at least one error case
3. The `docs/` documentation reflects any API or behaviour changes
4. The empirical metrics table in README.md is still accurate
5. `git log --oneline -5` shows clean, descriptive commit messages
6. The PR template checklist is complete
7. At least one reviewer has approved the PR
