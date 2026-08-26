# RescueCloud API Reference

Base URL: `http://localhost:8001` (dev) / `https://your-domain.com` (prod)

All authenticated endpoints require:
```
Authorization: Bearer <jwt_token>
```

---

## Authentication

### POST /auth/login
Returns a JWT access token.

**Request:**
```json
{ "username": "admin", "password": "your-password" }
```

**Response 200:**
```json
{ "access_token": "eyJ...", "token_type": "bearer" }
```

**Response 429:** Rate limit exceeded (5 attempts/60s per IP)

---

### GET /auth/me
Returns the current authenticated user.

**Response 200:**
```json
{ "username": "admin", "role": "admin" }
```

---

## Anomaly Detection

### POST /anomaly/predict
Scores an EHR audit event via the Isolation Forest model.

**Request:**
```json
{
  "role": "doctor",
  "action": "view_record",
  "failed_logins": 0,
  "requests_per_minute": 5,
  "records_accessed": 3,
  "records_modified": 0,
  "records_deleted": 0,
  "export_size_mb": 0.0,
  "session_duration_min": 20,
  "off_hours_access": 0,
  "new_ip_address": 0,
  "privilege_change": 0
}
```

**Response 200:**
```json
{ "prediction": "normal", "anomaly_score": 0.12, "inference_ms": 110.4 }
```

---

### GET /anomaly/blast-radius
Returns the current circuit-breaker containment state.

**Response 200 (no active containment):**
```json
{
  "circuit_breaker_active": false,
  "reaction_time_ms": 110.36,
  "rpo_guarantee": "Bounded by continuous WAL archiving (~4.06s empirical average)"
}
```

---

## Incidents

### GET /incidents
Returns paginated security incident history.

Query params: `limit` (1-100, default 20)

---

## Observability

### GET /metrics
Prometheus metrics in OpenMetrics text format.

Key metrics:
- `rescuecloud_anomalies_detected_total`
- `rescuecloud_circuit_breaker_active`
- `rescuecloud_http_request_duration_seconds`


## Error Codes

All errors follow RFC 7807 Problem Details format:
```json
{ "detail": "<human-readable message>" }
```

| Status | Meaning |
|---|---|
| 400 | Bad request — invalid payload or missing required fields |
| 401 | Unauthorized — missing or invalid JWT token |
| 403 | Forbidden — valid token but insufficient role |
| 422 | Validation error — Pydantic schema mismatch |
| 429 | Rate limited — exceeded login attempt threshold |
| 500 | Internal server error — check API logs |
| 503 | Service unavailable — circuit breaker active (write lockdown) |


## Authentication Flow

```
Client              API               Database
  |                   |                    |
  |-- POST /auth/login--> verify password  |
  |                   |--verify bcrypt hash->
  |                   |<--match/no match---|
  |<-- JWT token -----|
  |                   |
  |-- GET /incidents -->
  |   Authorization: Bearer <token>
  |                   |-- decode JWT ------>
  |                   |-- query incidents -->
  |<-- incident list--|
```


## Rate Limiting Details

The `POST /auth/login` endpoint enforces a fixed-window rate limit:

- **Window**: 60 seconds (configurable via `LOGIN_RATE_WINDOW_SECONDS`)
- **Limit**: 5 attempts per IP (configurable via `LOGIN_RATE_LIMIT`)
- **Response on exceed**: HTTP 429 with header `Retry-After: <seconds>`
- **Reset**: Automatically after the window expires

Other endpoints are NOT rate-limited in the current implementation.
Future work: add rate limiting to `/anomaly/predict` to prevent ML inference DoS.


## Prometheus Metrics Reference

Available at `GET /metrics` in OpenMetrics text format.

| Metric | Type | Description |
|---|---|---|
| `rescuecloud_http_requests_total` | Counter | Total HTTP requests by method, endpoint, status |
| `rescuecloud_http_request_duration_seconds` | Histogram | Request latency distribution |
| `rescuecloud_anomalies_detected_total` | Counter | Total anomalous events flagged |
| `rescuecloud_circuit_breaker_active` | Gauge | 1 if containment active, 0 if normal |
| `rescuecloud_quarantined_ips_count` | Gauge | Number of currently blocked IPs |
| `rescuecloud_login_attempts_total` | Counter | Login attempts by outcome |
| `rescuecloud_wal_switches_total` | Counter | Total WAL segment switches forced |


## WebSocket Support

RescueCloud does not currently expose a WebSocket API. The SOC dashboard
uses polling (`setInterval`) to refresh circuit breaker and blast-radius state.

Future work: replace polling with `GET /events` Server-Sent Events (SSE) stream.
This would reduce dashboard latency from 5s (poll interval) to near-real-time
and reduce server load by eliminating unnecessary polling during quiet periods.
