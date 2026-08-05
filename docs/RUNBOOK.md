# RescueCloud Production Runbook

## Health Check

```bash
# Check all services are running
kubectl get pods -n rescuecloud

# Check API health
curl https://your-domain.com/health

# Check Prometheus metrics
curl https://your-domain.com/metrics | grep rescuecloud_circuit_breaker_active
```

## Responding to a Circuit Breaker Trigger

1. **Confirm the alert** — check `/anomaly/blast-radius` to see which IPs were blocked
   and what triggered containment.
2. **Check blast radius** — review `blocked_ips` and `reason` in the response.
3. **If false positive** — reset the circuit breaker:
   ```bash
   curl -X POST https://your-domain.com/anomaly/reset      -H "Authorization: Bearer <admin-token>"
   ```
4. **If real incident** — do NOT reset. Allow the Healer to complete PITR recovery.
   Monitor `kubectl logs -n rescuecloud deploy/healer-service`.

## Checking WAL Archive Health

```bash
# Count WAL segments in S3 archive
aws s3 ls s3://your-wal-bucket/wal/ | wc -l

# Confirm archiving is active
kubectl exec -n rescuecloud postgres-primary-0 --   psql -U rescueadmin -c "SELECT pg_walfile_name(pg_current_wal_lsn());"
```

## Manual PITR Recovery

```bash
python3 scripts/smart_recover.py --compromise-time "2026-09-01 14:30:00"
```

See `docs/AWS_DEPLOYMENT.md` for the full recovery checklist.


## Rotating JWT Secret

When rotating `JWT_SECRET_KEY`:

1. Generate a new secret: `python3 -c 'import secrets; print(secrets.token_urlsafe(48))'`
2. Update the secret in AWS Secrets Manager.
3. ESO will sync the new value to the Kubernetes Secret within 1 hour (or force: `kubectl rollout restart`).
4. All existing JWTs will be invalidated immediately — users must re-login.
5. Verify API is operational: `curl https://your-domain.com/health`


## Scaling the Cluster

To handle increased EHR user load:

```bash
# Scale the API deployment
kubectl scale deployment rescuecloud-api --replicas=3 -n rescuecloud

# Verify all replicas are ready
kubectl get pods -n rescuecloud -l app=rescuecloud-api
```

**Note:** The circuit breaker state is in-memory per replica. For multi-replica
deployments, move `_CONTAINMENT_STATE` to Redis for shared state.
This is tracked in the System Maturity Roadmap (README.md).


## Upgrading RescueCloud

1. Review the changelog for breaking changes.
2. Test the new version in a staging environment against real (synthetic) data.
3. Take a manual backup: `python3 blockchain/register_latest_backup.py`
4. Update the Docker image tag in Kubernetes manifests.
5. Roll out with zero downtime: `kubectl rollout restart deploy/rescuecloud-api -n rescuecloud`
6. Verify: `kubectl rollout status deploy/rescuecloud-api -n rescuecloud`
7. Run smoke tests: `python3 scripts/health_check.py --host https://your-domain.com`


## Incident Response Levels

| Level | Trigger | Response |
|---|---|---|
| P1 Critical | Circuit breaker active + patient data at risk | Page on-call; initiate PITR immediately |
| P2 High | Anomaly detected but not yet circuit-broken | Alert security team; manual review within 1 hour |
| P3 Medium | False positive rate elevated | Review model; retrain if sustained for >3 days |
| P4 Low | Single anomalous event, no pattern | Log and monitor; no immediate action |


## Backup Failure Response

If `scripts/backup_stats.py` shows no backup in the last 24 hours:

1. Check backup sidecar: `docker compose ps backup-sidecar` or `kubectl get pods`
2. Check sidecar logs: `kubectl logs -n rescuecloud deploy/backup-sidecar --tail=50`
3. Check disk space: `df -h /var/lib/postgresql/backups`
4. Manually trigger a backup: `python3 scripts/backup.sh`
5. Verify blockchain registration: `python3 blockchain/register_latest_backup.py`
6. Page on-call if backup has been missing for > 4 hours


## Monitoring Alerts Reference

Configure these Prometheus alerting rules in `k8s/10-monitoring.yaml`:

| Alert | Condition | Severity | Action |
|---|---|---|---|
| CircuitBreakerActive | `rescuecloud_circuit_breaker_active == 1` | Critical | Page on-call |
| HighAnomalyRate | `rate(rescuecloud_anomalies_detected_total[5m]) > 0.5` | Warning | Review |
| NoBackupIn24h | No new backup file in 24h | Critical | Page on-call |
| HighLoginFailureRate | `rate(rescuecloud_login_attempts_total{outcome='failed'}[5m]) > 1` | Warning | Review |
| APIHighLatency | `histogram_quantile(0.95, ...) > 0.5` | Warning | Investigate |


## On-call Handoff Template

When handing off on-call responsibilities:

```
RescueCloud On-Call Handoff — [DATE]

Current status: [healthy / circuit breaker active / degraded]
Last incident: [date and brief description, or NONE]
Open alerts: [list, or NONE]
Pending changes: [list, or NONE]

Key contacts:
- Primary escalation: [name + phone]
- Blockchain node operator: [name + contact]
- AWS support case: [case number, if open]

Handoff notes: [any special context for the incoming on-call]
```
