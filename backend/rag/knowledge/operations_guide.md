# RescueCloud Operations Guide

Start the platform:

docker compose up -d --build

Import the Synthea dataset:

bash scripts/import_synthea.sh

Create a backup:

bash scripts/backup.sh

Restore the latest local backup:

bash scripts/recover_latest.sh

Restore a backup downloaded from MinIO:

bash scripts/recover_from_cloud.sh

Main backend health endpoint:

GET /health

Patient endpoint:

GET /patients

Isolation Forest model status:

GET /anomaly/model-status

Isolation Forest prediction endpoint:

POST /anomaly/predict

The RescueCloud dashboard allows users to:

- view patient records
- search patients
- check database health
- check Isolation Forest status
- test normal activity
- test suspicious activity
- view anomaly prediction results
