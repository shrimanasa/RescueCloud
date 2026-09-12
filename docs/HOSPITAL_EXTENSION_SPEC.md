# RescueCloud: Hospital EHR Database Resiliency Sidecar
## Technical Specification & Clinical Integration Guide

**Document Version:** 2.0  
**Target Audience:** Hospital Chief Information Security Officers (CISOs), Clinical IT Directors, Healthcare Infrastructure Architects, and SOC Teams.  
**Classification:** Technical Architecture & Compliance Specification  

---

## 1. Executive Summary & Clinical Scope

Modern healthcare delivery depends on continuous access to Electronic Health Record (EHR) databases. Ransomware attacks against hospital infrastructure (e.g., Change Healthcare, Universal Health Services, NHS Trusts) routinely compromise hospital databases, forcing clinicians to revert to paper charts and delaying critical patient interventions for days or weeks.

**RescueCloud** is engineered as a **non-invasive, out-of-band resiliency sidecar** for hospital EHR and clinical data platforms (e.g., PostgreSQL-backed FHIR servers, clinical data repositories, PACS metadata systems). 

### Clinical Guarantees & Constraints
- **Zero Latency on Clinical Transactions:** RescueCloud does **not** insert synchronous middleware or proxies into the clinician write path. Doctors and nurses interact directly with the EHR without any added latency.
- **Explicit Focus on Clinical Data Repositories:** RescueCloud safeguards relational database backends, clinical audit trails, and backup archives. It does not claim to replace hospital network perimeter firewalls or secure embedded medical device operating systems (infusion pumps, ventilators).
- **Empirical Recovery Bounds:** Demonstrated **12.71s mean RTO** (Recovery Time Objective) and **4.06s mean RPO** (Recovery Point Objective) on a verified Synthea clinical dataset (1,108 patients, 37,724 conditions).

---

## 2. Non-Invasive Sidecar Integration Topology

RescueCloud operates completely out-of-band from primary patient care transactions through two parallel data streams:

```text
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           HOSPITAL CLINICAL ZONE                                │
│                                                                                 │
│   Clinician Terminals / Mobile EHR            Primary EHR PostgreSQL Database   │
│   ┌──────────────────────────────┐            ┌─────────────────────────────┐   │
│   │ EHR Orders, Notes & Mar      │───────────▶│ Read/Write Primary Instance │   │
│   │ (Zero Added Middleware)      │            │ wal_level = replica         │   │
│   └──────────────────────────────┘            │ archive_mode = on           │   │
│                                               └──────────────┬──────────────┘   │
└──────────────────────────────────────────────────────────────┼──────────────────┘
                                                               │ Continuous WAL
                                                               │ Shipping (16MB)
┌──────────────────────────────────────────────────────────────┼──────────────────┐
│                      RESCUECLOUD RESILIENCY SIDECAR          │                  │
│                                                              ▼                  │
│   ┌────────────────────────────┐              ┌─────────────────────────────┐   │
│   │ Asynchronous Audit Tap     │              │ MinIO / AWS S3              │   │
│   │ (Kafka / Redis / Webhook)  │              │ Immutable WAL Archive       │   │
│   └─────────────┬──────────────┘              └──────────────┬──────────────┘   │
│                 │                                            │                  │
│                 ▼                                            ▼                  │
│   ┌────────────────────────────┐              ┌─────────────────────────────┐   │
│   │ Sentinel Agent (Port 8020) │              │ Auditor Agent (Port 8030)   │   │
│   │ - In-Process ML Inference  │              │ - SHA-256 Checksum Engine   │   │
│   │ - Air-Gap Circuit Breaker  │              │ - BackupLedger.sol Anchor   │   │
│   └─────────────┬──────────────┘              └──────────────┬──────────────┘   │
│                 │                                            │                  │
│                 │ Redis Pub/Sub Event Mesh (Port 6379)       │                  │
│                 └──────────────────────┬─────────────────────┘                  │
│                                        ▼                                        │
│                           ┌───────────────────────────┐                         │
│                           │ Healer Agent (Port 8040)  │                         │
│                           │ - Standby PITR Engine     │                         │
│                           │ - Replay WAL to T - ε     │                         │
│                           │ - Promote Clean Database  │                         │
│                           └───────────────────────────┘                         │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### Integration Streams:
1. **Continuous WAL Archival (`archive_command`):**
   The primary EHR PostgreSQL instance executes an archival command that transfers completed 16MB WAL segments into immutable object storage (AWS S3 or on-premise MinIO) via encrypted TLS connections.
2. **Asynchronous Audit Telemetry Tap:**
    mutating transactions, FHIR REST interactions, or HL7 v2/v3 operational event logs are mirrored asynchronously to the Sentinel Agent via Kafka, Redis, or HTTP event webhooks.

---

## 3. Empirical Research Benchmarks & Performance Data

Evaluated across 18 rigorous benchmark trials using a synthetic clinical dataset generated via Synthea (**1,108 patients**, **37,724 clinical conditions**) subjected to simulated rapid-encryption and mass-exfiltration ransomware:

| Metric | Conventional Snapshot Recovery | RescueCloud Resiliency Sidecar | Clinical & Operational Impact |
|---|---|---|---|
| **Clean Recovery Success Rate** | **0.0% (0/10 trials)** *(restored tainted/encrypted state)* | **100.0% (18/18 trials)** *(attack marker verified absent)* | Prevents restoring encrypted or poisoned database records |
| **Recovery Time Objective (RTO)** | ~0.17s *(naive restore of corrupted files)* | **12.71s mean** *(10.54s – 15.69s range)* | Clinical systems back online in under 16 seconds |
| **Recovery Point Objective (RPO)** | Hours / Days *(scheduled snapshot interval)* | **4.06s mean** *(3.00s – 6.00s range)* | Bounded by WAL segment shipping frequency |
| **ML Inference Latency** | None (Post-incident human discovery) | **110.36ms mean** *(63.59ms – 167.90ms range)* | Evaluates mutating activity before attackers entrench |
| **Integrity Verification Time** | None (Blind promotion of untrusted storage) | **10.39ms mean** *(7.46ms – 14.99ms range)* | Real-time SHA-256 deterministic mathematical validation |
| **Recovered Patients / Conditions** | 0 clean entities | **1,108 patients / 37,724 conditions** | 100% data integrity verified post-recovery |

> *Source: Empirical benchmark trials recorded in `results/research_metrics.csv` (18 trials) vs. `results/baseline_batch.csv` (10 trials).*

---

## 4. Autonomous Air-Gap Containment Protocol

When an attack is detected by the Threat Sentinel Agent (e.g., anomalous records accessed, abnormal export size, off-hours batch updates), RescueCloud initiates a three-step containment protocol:

1. **Client Quarantine & Session Revocation:**
   The offending IP address and authentication tokens are immediately quarantined at the gateway level.
2. **Emergency Read-Only Mode:**
   Mutating SQL operations (`INSERT`, `UPDATE`, `DELETE`) are immediately suspended on the primary database, preventing ransomware encryption loops or malicious wiping.
   *Crucial Clinical Feature:* Clinicians maintain uninterrupted read access to active charts, allergy records, and medications.
3. **Clean WAL Checkpoint Freeze (`pg_switch_wal()`):**
   The Sentinel executes `SELECT pg_switch_wal();` on the primary database, forcing PostgreSQL to immediately close and archive the active WAL log file. This guarantees that all transactions up to the exact moment of threat detection are safely committed to storage and separated from post-compromise activity.

---

## 5. Smart Point-In-Time Recovery (PITR) Workflow

When the SOC or Incident Commander initiates automated recovery:

1. **Candidate Query:** The Healer Agent queries `BackupLedger.sol` / internal ledger for the latest verified base backup preceding the incident timestamp $T_{incident}$.
2. **Cryptographic Validation:** Computes the SHA-256 checksum of the candidate image and validates it against the smart contract. If an attacker modified backup files, recovery halts immediately.
3. **Standby Instance Boot:** Launches an isolated PostgreSQL instance (port 5433 or secondary Kubernetes pod) with the base image.
4. **Deterministic WAL Replay:** Configures `recovery_target_time = T_{incident} - \epsilon` and mounts the archived WAL stream. PostgreSQL replays every transaction up to the exact second prior to compromise.
5. **Standby Promotion:** The instance promotes itself to read-write mode. Traffic is rerouted, restoring clinical database services in under 16 seconds.

---

## 6. HIPAA Security Rule Technical Safeguards Alignment

RescueCloud provides software technical safeguards that support covered entities and business associates in fulfilling **45 CFR Part 164 (HIPAA Security Rule)** requirements:

| HIPAA Section | Regulatory Standard | RescueCloud Safeguard Implementation |
|---|---|---|
| **§164.308(a)(7)(ii)(A)** | **Data Backup Plan** | Continuous PostgreSQL WAL archiving paired with scheduled base backups and cryptographic ledger receipts. |
| **§164.308(a)(7)(ii)(B)** | **Disaster Recovery Plan** | Automated Point-In-Time Recovery engine restoring clinical datasets in **12.71s mean RTO** with **4.06s mean RPO**. |
| **§164.308(a)(7)(ii)(C)** | **Emergency Mode Operation Plan** | Autonomous Air-Gap Circuit Breaker: sets EHR database to Read-Only mode during an active attack to preserve emergency clinician read access while halting destructive writes. |
| **§164.312(b)** | **Audit Controls** | Immutable Ethereum smart contract ledger (`BackupLedger.sol`) recording all backup checksums and recovery status transitions, preventing internal admin tampering. |
| **§164.312(c)(1)** | **Data Integrity** | Real-time SHA-256 cryptographic checksum verification of every candidate backup prior to promotion. |
| **§164.312(d)** | **Person or Entity Authentication** | Signed JWT bearer tokens with role-based access control (`admin`, `doctor`, `auditor`) and per-IP rate-limiting on login endpoints. |
| **§164.312(e)(1)** | **Transmission Security** | Production TLS 1.3 ingress termination via `cert-manager` Let's Encrypt and isolated Kubernetes network namespaces. |

---

## 7. Hospital Deployment & Implementation Checklist

For hospital IT and engineering teams integrating RescueCloud into enterprise clinical environments:

### Step 1: Network & Infrastructure Setup
- [ ] Provision dedicated Kubernetes namespace (`rescuecloud`) on private clinical cloud/VPC.
- [ ] Establish low-latency private interconnect / VPC peering between primary EHR PostgreSQL cluster and RescueCloud namespace.
- [ ] Configure S3 / MinIO bucket with Object Lock (WORM - Write Once, Read Many) for WAL archives.

### Step 2: EHR Database Configuration
- [ ] Enable PostgreSQL continuous archiving:
  ```ini
  wal_level = replica
  archive_mode = on
  archive_command = 'aws s3 cp %p s3://hospital-ehr-wal-archive/%f'
  archive_timeout = 60
  ```
- [ ] Provision dedicated least-privilege database user for circuit-breaker signaling (`SELECT pg_switch_wal()`).

### Step 3: Security & Identity Configuration
- [ ] Associate AWS IAM Role for Service Accounts (IRSA) with External Secrets Operator (`k8s/01-external-secrets.yaml`).
- [ ] Populate database credentials and JWT signing keys in AWS Secrets Manager.
- [ ] Apply edge TLS certificates via `cert-manager` Let's Encrypt issuer (`k8s/09-cert-issuer.yaml`).

### Step 4: Verification & Disaster Recovery Drills
- [ ] Execute test suite: `pytest` (26/26 tests passing).
- [ ] Run automated attack simulation and verify circuit-breaker engagement under 150ms.
- [ ] Conduct end-to-end PITR recovery drill to standby instance and verify patient condition count parity.


---

## Integration Example: Epic FHIR Sidecar

Add RescueCloud as a sidecar alongside your Epic pod. It watches the WAL stream and Redis audit bus without touching Epic DB tables.

```yaml
spec:
  containers:
    - name: rescuecloud-sentinel
      image: rescuecloud/sentinel:2.4.0
      env:
        - name: DB_HOST
          value: epic-postgres-primary
        - name: REDIS_HOST
          value: epic-redis
      resources:
        requests:
          cpu: 100m
          memory: 128Mi
        limits:
          cpu: 500m
          memory: 512Mi
```

Network policy: RescueCloud needs outbound to Postgres WAL port (5432), Redis (6379), AWS SM endpoint (443), S3 (443).


---

## Network Architecture

```
Clinicians -> EHR App -> PostgreSQL Primary
                                 |
                          Redis Pub/Sub -> RescueCloud Sentinel
                                                   |
                                          Auditor -> Healer
                                                        |
                                          S3 WAL Archive + AWS SM (IRSA)
```

RescueCloud sits entirely outside the EHR write path. It observes WAL and
Redis events as a read-only sidecar until containment triggers PITR recovery.
