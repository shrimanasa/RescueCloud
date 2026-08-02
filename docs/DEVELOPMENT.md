# RescueCloud Development Guide

## Prerequisites

- Python 3.11+
- PostgreSQL 16
- Redis 7
- Node.js 18+ (for blockchain/Hardhat)
- Docker + Docker Compose

## Quick Start

```bash
# Clone and set up environment
git clone git@github.com:shrimanasa/RescueCloud.git
cd RescueCloud
cp .env.example .env
# Edit .env with your local credentials

# Start dependencies
docker compose up -d postgres redis minio

# Install Python dependencies
pip install -r requirements.txt

# Run tests
pytest --tb=short -q

# Start the API
uvicorn backend.main:app --reload --port 8001
```

## Environment Variables

See `.env.example` for the full list. Required at minimum:
- `JWT_SECRET_KEY` (min 32 chars)
- `POSTGRES_*` connection vars
- `ADMIN_USERNAME` + `ADMIN_PASSWORD`

## Running the ML Pipeline

```bash
# Generate synthetic audit logs
python3 ml/generate_audit_logs.py

# Train the Isolation Forest model
python3 ml/train_isolation_forest.py

# Model is saved to ml/models/isolation_forest.joblib
```


## Blockchain Development

```bash
# Install Hardhat and compile contracts
cd blockchain
npm install
npx hardhat compile

# Start local Ethereum node
npx hardhat node

# In another terminal, deploy the contract
python3 blockchain/deploy_and_import_ledger.py

# Register a test backup
python3 blockchain/register_latest_backup.py
```


## RAG Knowledge Base

```bash
# Add knowledge documents
cp my_document.md rag/knowledge/

# Rebuild the vector store
python3 rag/build_vector_store.py

# Test a query
python3 rag/ask_rescuecloud.py 'How do I perform a PITR recovery?'
```

Do NOT commit `rag/vector_store/chroma.sqlite3` — it's excluded by .gitignore.


## Debugging Tips

```bash
# Watch real-time anomaly events
curl http://localhost:8001/metrics | grep anomaly

# Check circuit breaker state
curl http://localhost:8001/anomaly/blast-radius

# Trigger a test anomaly
TOKEN=$(curl -s -X POST http://localhost:8001/auth/login \
  -d 'username=admin&password=yourpassword' | jq -r .access_token)
curl -X POST http://localhost:8001/anomaly/predict \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"role":"admin","action":"export_data","export_size_mb":600,...}'
```


## IDE Setup

**VS Code:** Install extensions:
- `ms-python.python` (Python language server)
- `ms-python.black-formatter` (auto-format on save)
- `ms-vscode-remote.remote-containers` (devcontainer support)

Add to `.vscode/settings.json`:
```json
{
  "editor.formatOnSave": true,
  "python.defaultInterpreterPath": ".venv/bin/python",
  "python.testing.pytestEnabled": true,
  "python.testing.pytestArgs": ["tests"]
}
```


## Pre-commit Hooks

Install pre-commit to run checks before each commit:

```bash
pip install pre-commit
pre-commit install
```

Recommended `.pre-commit-config.yaml`:
```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.6.0
    hooks: [{id: ruff}, {id: ruff-format}]
  - repo: local
    hooks:
      - id: pytest
        name: pytest
        entry: pytest --tb=short -q
        language: system
        pass_filenames: false
```


## Profiling

To profile the anomaly detection middleware for performance bottlenecks:

```python
import cProfile, pstats
with cProfile.Profile() as profiler:
    # run your code
    pass
stats = pstats.Stats(profiler).sort_stats('cumulative')
stats.print_stats(20)
```

Key areas to profile:
- `anomaly_model.predict()` — should be < 50ms per request
- `anomaly_model.decision_function()` — should be < 50ms per request
- Redis publish in EventBus — should be < 5ms per event


## Useful Commands Reference

```bash
# Run tests with coverage
pytest --cov=backend --cov-report=term-missing

# Check for security vulnerabilities in dependencies
pip audit

# Format code
black backend/ tests/ ml/ scripts/

# Type check
mypy backend/ --ignore-missing-imports

# Generate audit logs and retrain model
python3 ml/generate_audit_logs.py && python3 ml/train_isolation_forest.py

# Run load test
locust -f locustfile.py --host=http://localhost:8001 --headless --users 20 --run-time 30s

# Check backup integrity
python3 blockchain/verify_latest_backup.py
```
