from __future__ import annotations

import os

import psycopg2
from fastapi import APIRouter, HTTPException, Query
from psycopg2.extras import RealDictCursor


router = APIRouter(
    prefix="/incidents",
    tags=["Security Incidents"],
)


def get_connection():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "rescuecloud-db"),
        port=int(os.getenv("DB_PORT", "5432")),
        database=os.getenv("DB_NAME", "rescuecloud"),
        user=os.getenv("DB_USER", "rescuecloud"),
        password=os.getenv("DB_PASSWORD", ""),
        cursor_factory=RealDictCursor,
    )


@router.get("")
def list_incidents(
    limit: int = Query(default=20, ge=1, le=100),
):
    connection = get_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT *
                FROM security_incidents
                ORDER BY detected_at DESC
                LIMIT %s;
                """,
                (limit,),
            )
            return cursor.fetchall()
    finally:
        connection.close()


@router.get("/latest")
def latest_incident():
    connection = get_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT *
                FROM security_incidents
                ORDER BY detected_at DESC
                LIMIT 1;
                """
            )

            incident = cursor.fetchone()

            if incident is None:
                return {
                    "message": "No security incidents recorded yet."
                }

            return incident
    finally:
        connection.close()


@router.get("/{incident_id}")
def get_incident(incident_id: int):
    connection = get_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT *
                FROM security_incidents
                WHERE incident_id = %s;
                """,
                (incident_id,),
            )

            incident = cursor.fetchone()

            if incident is None:
                raise HTTPException(
                    status_code=404,
                    detail="Security incident not found.",
                )

            return incident
    finally:
        connection.close()
