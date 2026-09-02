from __future__ import annotations

import logging
import os
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import psycopg2
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from psycopg2.extras import RealDictCursor
from pydantic import BaseModel

# Add parent directory to sys.path to access common
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from services.common.bus import get_event_bus
from services.common.events import AuditEvent, Channel

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [EHR-Service] %(message)s",
)
logger = logging.getLogger("rescuecloud.ehr")

app = FastAPI(title="RescueCloud EHR Core Service", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Lockdown state (read-only mode triggered during containment)
_READ_ONLY_LOCKDOWN = False
event_bus = get_event_bus()


def get_connection():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "rescuecloud-db"),
        port=int(os.getenv("DB_PORT", "5432")),
        database=os.getenv("DB_NAME", "rescuecloud_ehr"),
        user=os.getenv("DB_USER", "rescueadmin"),
        password=os.getenv("DB_PASSWORD", ""),
        cursor_factory=RealDictCursor,
    )


@app.middleware("http")
async def audit_and_lockdown_middleware(request: Request, call_next):
    global _READ_ONLY_LOCKDOWN
    method = request.method
    path = request.url.path
    client_ip = request.client.host if request.client else "127.0.0.1"

    # Enforce read-only lockdown if active
    if _READ_ONLY_LOCKDOWN and method in {"POST", "PUT", "PATCH", "DELETE"}:
        if not path.startswith("/ehr/"):
            logger.warning(f"BLOCKED {method} {path} from {client_ip} — Read-Only Emergency Lockdown is active!")
            return Response(
                content='{"detail":"EHR Database is in Air-Gap Read-Only Lockdown due to detected threat."}',
                status_code=423,  # Locked
                media_type="application/json",
            )

    response = await call_next(request)

    # Publish audit event for telemetry & anomaly detection
    if path != "/health":
        action_type = "query" if method == "GET" else "update" if method in {"PUT", "PATCH"} else "insert" if method == "POST" else "delete"
        event = AuditEvent(
            event_id=f"audit_{uuid.uuid4().hex[:12]}",
            method=method,
            path=path,
            client_ip=client_ip,
            action_type=action_type,
            payload_summary={"status_code": response.status_code},
        )
        event_bus.publish(Channel.EHR_AUDIT, event)

    return response


@app.get("/health")
def health():
    db_ok = False
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT 1;")
        conn.close()
        db_ok = True
    except Exception as e:
        logger.warning(f"EHR DB check failed: {e}")

    return {
        "status": "healthy" if db_ok else "degraded",
        "service": "ehr_service",
        "database_connected": db_ok,
        "lockdown_active": _READ_ONLY_LOCKDOWN,
    }


@app.get("/patients")
def list_patients(limit: int = 50, offset: int = 0):
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, first_name, last_name, gender, birthdate, city, state, healthcare_expenses
                FROM synthea_patients
                ORDER BY last_name, first_name
                LIMIT %s OFFSET %s;
                """,
                (limit, offset),
            )
            patients = cur.fetchall()
            cur.execute("SELECT count(*) as total FROM synthea_patients;")
            total_row = cur.fetchone()
            total = total_row["total"] if total_row else len(patients)
        conn.close()
        return {"total": total, "patients": patients}
    except Exception as exc:
        logger.error(f"Error fetching patients: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/patients/{patient_id}")
def get_patient(patient_id: str):
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM synthea_patients WHERE id = %s;",
                (patient_id,),
            )
            patient = cur.fetchone()
            if not patient:
                raise HTTPException(status_code=404, detail="Patient not found")

            cur.execute(
                "SELECT * FROM synthea_conditions WHERE patient_id = %s ORDER BY start_date DESC;",
                (patient_id,),
            )
            conditions = cur.fetchall()
        conn.close()
        return {"patient": patient, "conditions": conditions}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/ehr/lockdown")
def trigger_lockdown(payload: Dict[str, Any] = None):
    global _READ_ONLY_LOCKDOWN
    _READ_ONLY_LOCKDOWN = True
    logger.critical("EHR SERVICE LOCKED DOWN: Enforcing Read-Only mode across patient records.")
    return {"status": "locked", "read_only": True}


@app.post("/ehr/unlock")
def release_lockdown():
    global _READ_ONLY_LOCKDOWN
    _READ_ONLY_LOCKDOWN = False
    logger.info("EHR SERVICE UNLOCKED: Read-write mode restored.")
    return {"status": "unlocked", "read_only": False}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8010")))
