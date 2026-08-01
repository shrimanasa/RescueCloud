# RescueCloud System Architecture

## Overview

RescueCloud is a non-invasive hospital EHR database resiliency sidecar.
It monitors WAL streams and Redis audit events to detect anomalies and
orchestrate automated PITR recovery — without modifying the EHR write path.

## Component Diagram

```
EHR App ──► PostgreSQL Primary ──► WAL Archive (S3)
                │
           Redis Pub/Sub
                │
      ┌─────────┼─────────────┐
      ▼         ▼             ▼
  Sentinel   Auditor       Healer
  (detect)  (verify)     (recover)
      │         │             │
      └─────────┴─────────────┘
                │
         Gateway Commander
                │
         REST API / Dashboard
```

## Component Responsibilities

| Component | Role |
|---|---|
| Sentinel | Scores every POST/PUT/DELETE via Isolation Forest; triggers circuit breaker |
| Auditor | Verifies backup SHA-256 against on-chain ledger; nominates recovery candidate |
| Healer | Executes PITR recovery via WAL replay; promotes restored replica |
| Gateway | Unified REST API; incident commander; routes to microservices |

## Data Flow

1. EHR service emits `AuditEvent` to Redis `ehr:audit_events` channel
2. Sentinel scores event; if anomalous, publishes `ThreatDetectedEvent`
3. Auditor selects and verifies clean backup; publishes `CandidateBackupEvent`
4. Healer replays WAL to target time; publishes `RecoveryCompletedEvent`
5. Gateway resets circuit breaker; EHR returns to read-write mode


## Failure Modes

| Failure | RescueCloud Response |
|---|---|
| Postgres primary crash | CloudNativePG promotes standby automatically |
| Redis unavailable | EventBus falls back to local in-process pub/sub |
| Blockchain node down | Backup registration queued; verification degrades gracefully |
| S3 WAL archive unreachable | pg_archive_status shows failed segments; alert triggers |
| Isolation Forest OOM | Sidecar restarts; circuit breaker stays closed (safe default) |


## Scalability Considerations

The current architecture is sized for a single-hospital deployment with:
- Up to 500 concurrent EHR users
- Up to 1,000 audit events/second at peak
- Up to 100 GB of Postgres data

For multi-hospital deployments, consider:
- One RescueCloud instance per hospital (isolated blast radius)
- Shared Prometheus/Grafana monitoring with per-hospital dashboards
- Separate S3 WAL archive buckets per hospital for isolation


## Technology Stack

| Layer | Technology | Rationale |
|---|---|---|
| API | FastAPI + Uvicorn | Async-capable, auto-generates OpenAPI docs |
| ML | scikit-learn Isolation Forest | Unsupervised, no labelled training data needed |
| Database | PostgreSQL 16 | WAL-native PITR support, ACID guarantees |
| Cache/Bus | Redis 7 | Low-latency pub/sub for microservice events |
| Blockchain | Hardhat + Solidity | Tamper-proof backup ledger |
| Object Store | MinIO / S3 | WAL archive and backup blob storage |
| Orchestration | Kubernetes + CloudNativePG | HA Postgres, declarative infra |
| Secrets | AWS Secrets Manager + ESO | No static secrets in cluster |


## Security Zones

```
[ Internet ]
     |
[ ALB / Nginx Ingress + TLS ]
     |
[ RescueCloud API (port 8001) ] -- public zone
     |                    |
[ PostgreSQL :5432 ]  [ Redis :6379 ] -- private zone
     |                    |
[ S3 WAL Bucket ]  [ Secrets Manager ] -- AWS managed zone
     |
[ Hardhat / Ganache :8545 ] -- blockchain zone (internal only)
```


## Data Privacy Architecture

RescueCloud is designed to minimise ePHI exposure:

1. **WAL stream**: contains raw SQL changes — stored encrypted at rest in S3
2. **Audit events**: contain only metadata (role, action, counts) — no ePHI fields
3. **Blockchain**: stores only SHA-256 hashes and timestamps — no ePHI
4. **Incident log**: stores attack metadata, RPO/RTO — no ePHI
5. **ML model**: trained on synthetic data — no real patient information

The only component that accesses real ePHI is Postgres itself, which is
the existing EHR database that RescueCloud observes but does not own.


## Observability Stack

| Tool | Purpose | Access |
|---|---|---|
| Prometheus | Metrics collection and storage | `kubectl port-forward svc/prometheus 9090` |
| Grafana | Dashboards and alerting | `kubectl port-forward svc/grafana 3000` |
| Kubernetes events | Pod lifecycle and restarts | `kubectl get events -n rescuecloud` |
| Application logs | API and service logs | `kubectl logs -n rescuecloud deploy/rescuecloud-api` |

Key Grafana dashboards to create:
- Circuit breaker status over time
- Anomaly detection rate by attack type
- RTO/RPO trend over recovery events
- ML inference latency percentiles


## Future Architecture Roadmap

| Item | Priority | Complexity |
|---|---|---|
| Move circuit breaker state to Redis | High | Medium |
| Replace polling with SSE for dashboard | Medium | Low |
| Add WebSocket for real-time anomaly alerts | Medium | Medium |
| Implement token refresh endpoint | Low | Low |
| Add multi-hospital tenant isolation | High | High |
| FHIR R4 API adapter for Epic/Cerner integration | High | High |
| Replace Hardhat with production EVM (Polygon) | Medium | Medium |


## Glossary

| Term | Definition |
|---|---|
| **WAL** | Write-Ahead Log — Postgres transaction log used for PITR and replication |
| **PITR** | Point-In-Time Recovery — restore database to state at exact timestamp |
| **RPO** | Recovery Point Objective — maximum acceptable data loss window |
| **RTO** | Recovery Time Objective — maximum acceptable service downtime |
| **ESO** | External Secrets Operator — Kubernetes operator syncing cloud secrets |
| **IRSA** | IAM Roles for Service Accounts — AWS mechanism for pod-level IAM |
| **ePHI** | Electronic Protected Health Information — HIPAA-regulated patient data |


## Deployment Checklist

Before going live with real patient data:

- [ ] EKS cluster running with HA configuration
- [ ] CloudNativePG 3-node cluster healthy
- [ ] ESO syncing secrets from AWS Secrets Manager
- [ ] TLS cert issued and valid (check cert-manager Certificate status)
- [ ] Prometheus scraping all services
- [ ] Grafana dashboards configured
- [ ] Backup sidecar running and registering on-chain
- [ ] Penetration test completed and findings remediated
- [ ] BAA signed with AWS
- [ ] HIPAA risk assessment completed
- [ ] Incident response plan documented and tested
- [ ] Staff training completed
