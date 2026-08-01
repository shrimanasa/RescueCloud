# RescueCloud: Hospital EHR Database Resiliency Sidecar

**Non-invasive, out-of-band ransomware defense and near-zero RPO recovery sidecar for clinical Electronic Health Record (EHR) databases.**

RescueCloud attaches to existing hospital EHR databases (e.g., PostgreSQL-backed FHIR stores, clinical data warehouses) without modifying EHR vendor application code or introducing latency onto the clinical write path. By pairing continuous Write-Ahead Log (WAL) archiving with out-of-band ML threat detection and cryptographic integrity verification, RescueCloud bounds data loss to seconds ($\text{RPO} \approx 4.06\text{s}$) and restores clinical continuity in under 16 seconds ($\text{RTO} \approx 12.71\text{s}$).

---

## Key Pillars

1. **Continuous Archiving & Near-Zero RPO Point-In-Time Recovery (PITR)**:
   PostgreSQL write-ahead logging (`wal_level=replica`, `archive_mode=on`) continuously ships 16MB WAL segments into `/wal_archive`. When an attack is flagged at timestamp $T$, the system replays transactions strictly up to $T - \epsilon$, achieving bounded near-zero data loss ($\text{RPO} \approx 4.06\text{s}$ empirical mean, bounded by WAL segment shipping frequency).

2. **In-Process ML Anomaly Detection**:
   Isolation Forest model (300 estimators, `contamination=0.045`) evaluates mutating transactions in ~110.36ms mean inference latency. Features automated air-gap containment, IP quarantining, and checkpoint freezing via `pg_switch_wal()`.

3. **Cryptographic Blockchain Ledger (`BackupLedger.sol`)**:
   Immutable Ethereum/Hardhat smart contract registering backup hashes and status transitions (`Eligible`, `Rejected`, `Selected`, `Restored`), ensuring zero internal tampering even under database superuser compromise.

4. **Autonomous Multi-Agent Incident Response & Microservices**:
   Event-driven microservices (EHR Core, Threat Sentinel Agent, Blockchain Auditor Agent, PITR Healer Agent, API Gateway & Commander Agent) communicating over a Redis Pub/Sub mesh.

5. **RAG Incident Response Assistant**:
   Vector database knowledge base (`rag/`) powered by ChromaDB for contextual incident runbooks and SOC decision support.

---

## Empirical Research Benchmarks

Evaluated against a clinical dataset generated via Synthea (**1,108 patients**, **37,724 clinical conditions**) across 18 benchmark trials under active ransomware attack simulation:

| Metric | Conventional Disaster Recovery (Snapshot Baseline) | RescueCloud Sidecar (Continuous WAL + Smart PITR) | Clinical Impact |
|---|---|---|---|
| **Clean Recovery Success Rate** | **0.0% (0/10 trials)** *(restored infected/tampered latest state)* | **100.0% (18/18 trials)** *(attack marker verified absent)* | Prevents restoring encrypted or poisoned database state |
| **Recovery Time Objective (RTO)** | ~0.17s *(naive restore of infected snapshot)* | **12.71s mean** *(min: 10.54s, max: 15.69s)* | Full clinical database rollback in under 16 seconds |
| **Recovery Point Objective (RPO)** | Hours / Days *(scheduled snapshot interval)* | **4.06s mean** *(min: 3.00s, max: 6.00s)* | Near-zero clinical record loss |
| **ML Inference Latency** | None (Post-incident manual discovery) | **110.36ms mean** *(min: 63.59ms, max: 167.90ms)* | Intercepts exfiltration and ransomware before persistence |
| **Cryptographic Hash Verification** | None (Blind promotion of untrusted files) | **10.39ms mean** *(min: 7.46ms, max: 14.99ms)* | Halts recovery if candidate backup was tampered with |
| **Recovered Clinical Entities** | 0 clean conditions | **1,108 patients / 37,724 conditions** | 100% verified clinical dataset integrity |

> *Source: Empirical benchmark trials recorded in `results/research_metrics.csv` (18 trials) vs. `results/baseline_batch.csv` (10 trials).*

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

```text
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
Open [http://localhost:3000](http://localhost:3000) in your browser.

---

## Anomaly Detection Performance

- **Algorithm**: Isolation Forest (300 estimators, `contamination=0.045`)
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
5. **Bounded Data Loss**: RPO bounded by WAL archival boundary ($\text{RPO} \approx 4.06\text{s}$ empirical mean under continuous archive mode).

---

## HIPAA Security Rule Technical Safeguards Alignment

RescueCloud provides software technical safeguards supporting covered entities and business associates under the **HIPAA Security Rule (45 CFR Part 164)**:

| HIPAA Security Rule Provision | Legal Requirement | RescueCloud Technical Control |
|---|---|---|
| **§164.308(a)(7)(ii)(A)** | **Data Backup Plan** | Continuous PostgreSQL WAL archiving with automated base snapshots and cryptographic ledger indexing. |
| **§164.308(a)(7)(ii)(B)** | **Disaster Recovery Plan** | Automated Point-In-Time Recovery (PITR) engine achieving **12.71s mean RTO** and **4.06s mean RPO**. |
| **§164.308(a)(7)(ii)(C)** | **Emergency Mode Operation Plan** | Autonomous Air-Gap Circuit Breaker: locks EHR database to Read-Only mode upon threat detection, preserving clinician read access to patient histories while halting destructive writes. |
| **§164.312(b)** | **Audit Controls** | Immutable on-chain smart contract ledger (`BackupLedger.sol`) recording all backup checksums and recovery events, preventing internal admin tampering. |
| **§164.312(c)(1)** | **Data Integrity** | Real-time SHA-256 cryptographic verification of all candidate backups prior to promotion, guaranteeing zero tampering. |
| **§164.312(d)** | **Person or Entity Authentication** | Signed JWT bearer tokens with role-based access control (`admin`, `doctor`, `auditor`) and per-IP rate-limiting on login endpoints. |
| **§164.312(e)(1)** | **Transmission Security** | Production TLS 1.3 ingress termination via `cert-manager` Let's Encrypt and isolated Kubernetes network namespaces. |

> *Disclaimer: RescueCloud provides software technical safeguards that support HIPAA compliance. Full organizational compliance requires administrative procedures, workforce training, physical safeguards, and executed Business Associate Agreements (BAAs).*

---

## Production Kubernetes Infrastructure

The `k8s/` directory provides production-hardened manifests wired into `k8s/kustomization.yaml`:

1. **AWS Secrets Manager via External Secrets Operator (`k8s/01-external-secrets.yaml`)**:
   IRSA-authenticated synchronization of database passwords, JWT signing keys, and MinIO credentials from AWS Secrets Manager—no static secrets in git.
2. **PostgreSQL High Availability (`k8s/03-postgres-ha.yaml`)**:
   CloudNativePG 3-instance cluster configured with synchronous replication (`synchronous_commit: "on"`, `minSyncReplicas: 1`) across multi-AZ failure domains.
3. **Edge TLS & Security Headers (`k8s/09-ingress.yaml`, `k8s/09-cert-issuer.yaml`)**:
   Nginx Ingress Controller coupled with `cert-manager` Let's Encrypt automated certificate issuance and strict security headers (`HSTS`, `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`).
4. **Prometheus Telemetry Mesh (`k8s/10-monitoring.yaml`)**:
   Continuous scrape of `/metrics` tracking request duration histograms, anomaly counts, circuit-breaker activations, and `pg_switch_wal()` executions.
5. **Gateway Rate Limiting**:
   Fixed-window IP rate limiting throttling repeated authentication attempts on `/auth/login` (`429 Too Many Requests` + `Retry-After`).

For deployment instructions on AWS EKS, refer to the [AWS Deployment Guide](docs/AWS_DEPLOYMENT.md).

---

## System Maturity & Production Hardening Roadmap

RescueCloud is a validated research prototype with production-ready infrastructure blueprints, not yet an enterprise SaaS deployment. The boundary between our verified implementation and hospital enterprise operationalization is stated explicitly:

### Validated Core Contributions (Proven & Working)
- **Near-Zero RPO Cold Recovery**: PostgreSQL continuous WAL archiving with deterministic PITR replay to a target timestamp ($12.71\text{s}$ mean RTO, $4.06\text{s}$ mean RPO, 100% clean recovery across 18 trials).
- **In-Process ML Detection**: Isolation Forest scoring of mutating transactions with dynamic latency tracking ($110.36\text{ms}$ mean), triggering automated air-gap containment and `pg_switch_wal()`.
- **Out-of-Band Cryptographic Ledger**: An Ethereum smart contract (`BackupLedger.sol`) and deterministic SHA-256 validation ($10.39\text{ms}$ mean) that rejects promotion of corrupted backups even under database superuser compromise.
- **Autonomous Multi-Agent Architecture**: Event-driven incident handling across Sentinel, Auditor, and Healer services over Redis Pub/Sub.
- **Automated Verification**: Full CI test suite covering auth/JWT, fail-fast secret validation, rate limiting, and integrity verification (26 passing tests).

### Limitations — Enterprise Hardening Roadmap
1. **Edge TLS & Live Ingress**: Manifests exist in `k8s/09-ingress.yaml` and `k8s/09-cert-issuer.yaml` (cert-manager Let's Encrypt), but live DNS and public ACME HTTP-01 challenges require an active domain and running cluster before handling live patient PHI (HIPAA §164.312(e)(1)).
2. **Observability Mesh & Alerting**: Native `/metrics` endpoint and Prometheus `ServiceMonitor` are implemented in `k8s/10-monitoring.yaml`, but PagerDuty/Alertmanager integration and production Grafana persistence are pending live cluster provisioning.
3. **Cloud Secrets Manager**: AWS Secrets Manager manifests via External Secrets Operator (`k8s/01-external-secrets.yaml`) are wired into Kustomize, but live cloud operation requires binding the AWS IRSA IAM role and KMS key in the target AWS account.
4. **High Availability Replication**: CloudNativePG HA cluster (`k8s/03-postgres-ha.yaml`) with 3 synchronous replicas is defined for zero-loss failover, but live cross-AZ failover drills require real cloud persistent volumes (EBS gp3).
5. **Perimeter WAF & Distributed Rate Limiting**: Fixed-window IP rate limiting is implemented on `/auth/login` in Python; distributed token-bucket rate limiting via Redis cluster and perimeter cloud WAF (AWS WAF / Cloudflare) are enterprise enhancements.

> *These five items define the explicit boundary between this validated research prototype and commercial clinical hospital deployment.*

---

## Hospital Integration & Technical Specification

For detailed architectural specifications, HL7/FHIR event ingestion schemas, out-of-band WAL replication topology, and clinical continuity procedures, consult the [Hospital Extension Specification](docs/HOSPITAL_EXTENSION_SPEC.md).



---

## Changelog

### v2.4.0 (2026-09-13)
- Dynamic time.perf_counter() inference latency measurement
- Empirical benchmarks derived from results/research_metrics.csv
- HIPAA Security Rule alignment table
- System Maturity Roadmap section restored

### v2.3.0 (2026-09-08)
- AWS Secrets Manager via IRSA (no static keys)
- CloudNativePG 3-node HA Postgres manifest
- TLS ingress + cert-manager + Prometheus observability
- Fixed kustomization.yaml wiring bug

### v2.2.0 (2026-09-07)
- JWT auth + RBAC, fail-closed on missing secrets
- Per-IP rate limiter on /auth/login (HTTP 429)
- WAL archive purged from git history

---

## Contributing

1. Fork and branch — never commit directly to main.
2. Run `pytest --tb=short -q` before opening a PR.
3. Do not commit PHI — wal_archive/, backups/, data/synthea/ are gitignored.
4. Update empirical metrics by re-deriving values from the CSV, not rounding.
