# RescueCloud Project Overview

RescueCloud is a healthcare EHR backup, security monitoring, and disaster recovery platform.

The system uses:

- PostgreSQL for EHR data
- FastAPI for backend APIs
- Nginx for the frontend
- Docker and Docker Compose for containers
- MinIO for local object storage
- SHA-256 for backup integrity verification
- Isolation Forest for suspicious activity detection
- Synthea synthetic healthcare data

The EHR dataset contains:

- 1,108 synthetic patients
- 37,724 condition records

No real patient data is used.

Main services:

- Frontend: http://localhost:3000
- Main backend: http://127.0.0.1:8001
- Recovery backend: http://127.0.0.1:8002
- PostgreSQL: localhost:5432
- Recovery PostgreSQL: localhost:5433
- MinIO console: http://localhost:9001
