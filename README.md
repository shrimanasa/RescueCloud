# RescueCloud

**Ransomware-resilient EHR backup and recovery platform with in-process ML anomaly detection, blockchain-verified cryptographic integrity, and PostgreSQL Point-In-Time Recovery (PITR).**

---

## Key Pillars

1. **Continuous Archiving & Zero-RPO Point-In-Time Recovery (PITR)**:
   PostgreSQL write-ahead logging (`wal_level=replica`, `archive_mode=on`) continuously ships 16MB WAL segments into `/wal_archive`. When an attack is flagged at timestamp $T$, the system replays transactions strictly up to $T - \epsilon$, achieving verifiable zero data loss ($RPO = 0s$).
2. **In-Process ML Anomaly Detection**:
   Isolation Forest model (300 estimators, `contamination=0.045`) evaluates mutating transactions in ~2ms. Features automated air-gap containment, IP quarantining, and checkpoint freezing via `pg_switch_wal()`.
3. **Cryptographic Blockchain Ledger (`BackupLedger.sol`)**:
   Immutable Ethereum/Hardhat smart contract registering backup hashes and status transitions (`Eligible`, `Rejected`, `Selected`, `Restored`).
4. **Autonomous Multi-Agent Incident Response & Microservices**:
   Event-driven microservices (EHR Core, Threat Sentinel Agent, Blockchain Auditor Agent, PITR Healer Agent, API Gateway & Commander Agent) communicating over a Redis Pub/Sub mesh.
5. **RAG Incident Response Assistant**:
   Vector database knowledge base (`rag/`) powered by ChromaDB for contextual incident runbooks and SOC decision support.

---

## Threat Model & Blockchain Justification

### Why Blockchain in Backup & Recovery?
In sophisticated healthcare ransomware campaigns, adversaries often escalate privileges to obtain root database credentials (`rescueadmin`). If backup metadata and audit histories reside solely within internal PostgreSQL tables (`backup_ledger`), a compromised superuser can tamper with checksums, falsify timestamps, or wipe the ledger.

**RescueCloud's Defense-in-Depth Solution:**
- **Out-of-Band Cryptographic Immutability**: Base backup SHA-256 digests, timestamps, and record counts are committed to the on-chain smart contract (`BackupLedger.sol`).
- **Tamper Verification**: During recovery, the Auditor Agent verifies candidate backups against the blockchain state. If an adversary attempts to substitute a corrupted snapshot or alter historical timestamps, the smart contract verification fails and halts recovery before corrupt data can be restored.

---

## System Architecture

RescueCloud supports two deployment topologies:

### Option 1: Distributed Microservices & Multi-Agent Architecture (`docker-compose.microservices.yml`)
Deconstructs the platform into fault-isolated microservices with dedicated autonomous agents:

```
┌────────────────────────────────────────────────────────────────────────┐
│                        SOC Dashboard UI (Port 3000)                    │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                         ┌──────────▼──────────┐
                         │ API Gateway (8001)  │
                         │ Commander Agent     │
                         └──────────┬──────────┘
                                    │
         ┌──────────────────────────┼──────────────────────────┐
         │                          │                          │
┌────────▼────────┐        ┌────────▼────────┐        ┌────────▼────────┐
│ EHR Service     │        │ Sentinel Agent  │        │ Auditor Agent   │
│ Port 8010       │        │ Port 8020       │        │ Port 8030       │
│ (PostgreSQL DB) │        │ (ML Scoring)    │        │ (Ledger/MinIO)  │
└────────┬────────┘        └────────┬────────┘        └────────┬────────┘
         │                          │                          │
         └──────────────────────────┼──────────────────────────┘
                                    │ Redis Pub/Sub (Port 6379)
                           ┌────────▼────────┐
                           │ Healer Agent    │
                           │ Port 8040       │
                           │ (PITR Engine)   │
                           └─────────────────┘
```

| Service / Container | Port | Role & Agent |
|---|---|---|
| `rescuecloud-gateway` | 8001 | API Gateway & **Incident Commander Agent** (Routes traffic, RAG SOC assistant) |
| `rescuecloud-ehr-service` | 8010 | **EHR Core Service** (Patient records, CRUD operations, audit stream emitter) |
| `rescuecloud-sentinel-service` | 8020 | **Threat Sentinel Agent** (In-process ML scoring, blast radius, air-gap circuit breaker) |
| `rescuecloud-auditor-service` | 8030 | **Blockchain Auditor Agent** (MinIO sync, SHA-256 verification, smart contract sync) |
| `rescuecloud-healer-service` | 8040 | **PITR Healer Agent** (Automated WAL replay engine, recovery DB promotion) |
| `rescuecloud-redis` | 6379 | Redis Pub/Sub Event Mesh |
| `rescuecloud-db` | 5432 | Primary PostgreSQL (EHR data with continuous WAL archiving) |
| `rescuecloud-minio` | 9000/9001 | MinIO S3 Object Storage (Base backups & WAL segments) |
| `rescuecloud-frontend` | 3000 | Dark-themed SOC Dashboard (Nginx) |

---

### Option 2: Classic Monolithic Deployment (`docker-compose.yml`)
A consolidated single-backend container (`rescuecloud-backend-container` on port 8001) ideal for single-node research evaluation, benchmarking, and quick demonstrations.

---

## Quickstart

### 1. Environment Setup
```bash
cp .env.example .env
# Configure POSTGRES_PASSWORD and MINIO_ROOT_PASSWORD
```

### 2. Start the Stack

**Microservices Architecture (Recommended):**
```bash
docker compose -f docker-compose.microservices.yml up -d --build
```

**Classic Monolithic Stack:**
```bash
docker compose up -d --build
```

### 3. Create Initial Base Backup
```bash
bash scripts/base_backup.sh
```

### 4. Train Anomaly Detection Model
```bash
python3 ml/generate_audit_logs.py      # generates 50,000 synthetic audit events
python3 ml/train_isolation_forest.py   # trains model + produces threshold sweep table
```

### 5. Run Multi-Agent Integration Tests
```bash
python3 scripts/test_multiagent_flow.py
```

### 6. Access SOC Dashboard
Open `http://localhost:3000` in your browser.

---

## Anomaly Detection Performance

- **Algorithm**: Isolation Forest (300 estimators, contamination=0.045)
- **Dataset**: 50,000 synthetic clinical audit events (5.0% true attack rate)

| Operating Mode | Anomaly Threshold | Recall (Sensitivity) | Precision (Purity) | F1 Score |
|---|---|---|---|---|
| **Default Production Baseline** | **0.00** | **79.0%** | **84.8%** | **81.8%** |
| **High-Security Defense** | **0.05** | **95.0%** | **58.9%** | **72.7%** |

---

## Load & Attack Simulation
```bash
pip install locust
locust -f locustfile.py --host http://localhost:8001
# Locust Web UI: http://localhost:8089
```

---

## Point-In-Time Recovery (PITR) Execution

When an attack or corruption event is flagged at timestamp $T$:
```bash
python3 scripts/smart_recover.py --compromise-time "YYYY-MM-DD HH:MM:SS"
```
1. **Candidate Query**: Queries `backup_ledger` / smart contract for the latest verified base backup before $T$.
2. **Integrity Check**: Computes SHA-256 hash to confirm zero tampering.
3. **WAL Replay**: Mounts `/wal_archive` into isolated recovery database (port 5433) and sets `recovery_target_time = T`.
4. **Promotion**: PostgreSQL replays transaction logs up to the exact target second, stops, and promotes to read-write.
5. **Zero Data Loss**: Verifiable RPO gap $= 0.0\text{s}$.
