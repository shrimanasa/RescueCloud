# RescueCloud Security Model

## Authentication

All API endpoints (except `/auth/login` and `/metrics`) require a valid JWT
Bearer token issued by `POST /auth/login`.

- Tokens are HS256-signed with a secret key of at least 32 characters.
- The API is **fail-closed**: if `JWT_SECRET_KEY` is missing or too short at
  startup, the process exits immediately rather than running unsecured.
- Tokens expire after `ACCESS_TOKEN_EXPIRE_MINUTES` (default: 60 minutes).

## Authorization

Role-based access control (RBAC) is enforced via `require_role()`:

| Endpoint | Required Role |
|---|---|
| `POST /anomaly/reset` | `admin` |
| `GET /incidents` | Any authenticated user |
| `POST /anomaly/predict` | Any authenticated user |

## Rate Limiting

`POST /auth/login` is rate-limited to 5 attempts per IP per 60 seconds.
Exceeding the limit returns HTTP 429 with a `Retry-After` header.

## Secrets Management

In production (AWS EKS), all secrets are stored in AWS Secrets Manager
and synced into the cluster via External Secrets Operator (ESO) + IRSA.
No static credentials are stored in Kubernetes Secrets or environment files.

## Known Limitations

See `README.md → System Maturity & Production Hardening Roadmap` for the
current list of unresolved security gaps before production deployment.


## Dependency Security

Run `pip audit` regularly to check for known vulnerabilities in Python dependencies.
Key dependencies and their security implications:

| Package | Purpose | Key security consideration |
|---|---|---|
| `bcrypt` | Password hashing | Keep BCRYPT_ROUNDS >= 10 (OWASP) |
| `pyjwt` | JWT signing | Verify `algorithms=['HS256']` explicitly |
| `fastapi` | Web framework | Keep updated for security patches |
| `psycopg2` | Postgres driver | Use parameterised queries only |
| `web3` | Blockchain client | Pin to a specific version |


## Secrets Lifecycle

| Secret | Rotation Frequency | How to Rotate |
|---|---|---|
| `JWT_SECRET_KEY` | 90 days | Update in AWS Secrets Manager; ESO syncs automatically |
| `ADMIN_PASSWORD` | 30 days | Update in AWS Secrets Manager |
| `DB_PASSWORD` | 90 days | CloudNativePG password rotation + Secrets Manager update |
| Blockchain private key | On compromise | Re-deploy contract; migrate ledger via export/import |


## Network Security

In production Kubernetes:

- All inter-service communication uses in-cluster DNS (never public IPs)
- The only public-facing endpoint is the Nginx ingress with TLS termination
- Postgres, Redis, and blockchain RPC ports are NOT exposed outside the cluster
- Use NetworkPolicy resources to restrict pod-to-pod communication
- Enable AWS VPC endpoint for S3 and Secrets Manager (no public internet required)


## CORS Configuration

CORS is scoped to the origins listed in the `CORS_ORIGINS` environment variable.
Default allowed origins: `http://localhost:3000`, `http://localhost:5500`,
`http://localhost:8000`, `http://localhost:8001`.

In production, set `CORS_ORIGINS` to only your hospital's frontend domain:
```
CORS_ORIGINS=https://ehr-dashboard.your-hospital.com
```
Never use `*` (wildcard) in production — it allows any website to make
credentialed requests to the API, bypassing browser same-origin protection.


## Incident Logging

All security incidents are written to `security_incidents` table with:
- `detected_at`: exact timestamp of anomaly detection
- `estimated_compromise_at`: estimated start of breach window
- `attack_type`: category of attack detected
- `rto_seconds`: time from detection to service restoration
- `rpo_seconds`: estimated data loss window

This log is the primary evidence for HIPAA breach notification timelines.
Under HIPAA, covered entities must notify affected individuals within 60 days
of discovery. `detected_at` is the discovery timestamp.


## Container Security

- Run all containers as non-root users (add `USER 1000` to Dockerfiles)
- Use `securityContext.readOnlyRootFilesystem: true` in Kubernetes pods where possible
- Scan images for CVEs before deployment: `trivy image rescuecloud/api:2.4.0`
- Use distroless or alpine base images to minimise attack surface
- Enable Kubernetes Pod Security Standards (restricted policy) for the namespace


## Third-Party Integrations

If integrating RescueCloud with external security tools:

- **SIEM (Splunk/ELK)**: Forward `/metrics` output and application logs via Prometheus remote write
- **SOAR**: Trigger playbooks via webhook on `rescuecloud_circuit_breaker_active == 1`
- **EDR**: Share blocked IPs from `/anomaly/blast-radius` for network-level blocking
- **Ticketing (Jira/ServiceNow)**: Create incidents automatically when circuit breaker trips

All integrations should use read-only API keys — never share admin credentials.


## Pen Test Scope

When commissioning a penetration test, provide the following scope:

- **In scope**: REST API (`/auth/*`, `/anomaly/*`, `/incidents`), JWT handling,
  rate limiting bypass attempts, CORS policy, authentication edge cases
- **Out of scope**: Kubernetes control plane, AWS account-level attacks,
  blockchain node (Hardhat is local dev only)
- **Test environment**: Use the staging cluster only — never test against production
- **Credentials**: Provide a non-admin test account; the pen tester should not
  have prior knowledge of the JWT secret
