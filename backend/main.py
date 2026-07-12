import os
from pathlib import Path

import joblib
import pandas as pd
import psycopg2
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field


app = FastAPI(title="RescueCloud API")

MODEL_PATH = (
    Path(__file__).resolve().parent
    / "models"
    / "isolation_forest.joblib"
)

try:
    anomaly_model = joblib.load(MODEL_PATH)
except Exception as error:
    anomaly_model = None
    model_error = str(error)


class ActivityEvent(BaseModel):
    role: str
    action: str
    status: str = "success"

    failed_logins: int = Field(default=0, ge=0)
    requests_per_minute: int = Field(default=1, ge=0)
    records_accessed: int = Field(default=0, ge=0)
    records_modified: int = Field(default=0, ge=0)
    records_deleted: int = Field(default=0, ge=0)
    export_size_mb: float = Field(default=0.0, ge=0)
    session_duration_min: int = Field(default=1, ge=0)

    off_hours_access: int = Field(default=0, ge=0, le=1)
    new_ip_address: int = Field(default=0, ge=0, le=1)
    privilege_change: int = Field(default=0, ge=0, le=1)


def get_connection():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "5432")),
        database=os.getenv("DB_NAME", "rescuecloud_ehr"),
        user=os.getenv("DB_USER", "rescueadmin"),
        password=os.environ["DB_PASSWORD"],
    )


@app.get("/")
def home():
    return {
        "message": "RescueCloud backend is running",
        "anomaly_model_loaded": anomaly_model is not None,
    }


@app.get("/patients")
def get_patients():
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        p.id::text,
                        CONCAT_WS(
                            ' ',
                            p.first_name,
                            p.middle_name,
                            p.last_name
                        ) AS patient_name,
                        EXTRACT(
                            YEAR FROM AGE(
                                COALESCE(p.deathdate, CURRENT_DATE),
                                p.birthdate
                            )
                        )::INTEGER AS age,
                        CASE
                            WHEN p.gender = 'M' THEN 'Male'
                            WHEN p.gender = 'F' THEN 'Female'
                            ELSE p.gender
                        END AS gender,
                        COALESCE(
                            latest_condition.description,
                            'No recorded condition'
                        ) AS diagnosis
                    FROM synthea_patients AS p
                    LEFT JOIN LATERAL (
                        SELECT c.description
                        FROM synthea_conditions AS c
                        WHERE c.patient_id = p.id
                        ORDER BY
                            CASE
                                WHEN c.stop_date IS NULL THEN 0
                                ELSE 1
                            END,
                            c.start_date DESC,
                            c.condition_id DESC
                        LIMIT 1
                    ) AS latest_condition ON TRUE
                    ORDER BY p.first_name, p.last_name;
                    """
                )

                rows = cursor.fetchall()

        return [
            {
                "patient_id": row[0],
                "name": row[1],
                "age": row[2],
                "gender": row[3],
                "diagnosis": row[4],
            }
            for row in rows
        ]

    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=f"Database query failed: {error}",
        )


@app.get("/anomaly/model-status")
def anomaly_model_status():
    if anomaly_model is None:
        return {
            "status": "error",
            "loaded": False,
            "detail": model_error,
        }

    return {
        "status": "ready",
        "loaded": True,
        "model": "Isolation Forest",
    }


@app.post("/anomaly/predict")
def predict_anomaly(event: ActivityEvent):
    if anomaly_model is None:
        raise HTTPException(
            status_code=503,
            detail="Isolation Forest model is unavailable.",
        )

    try:
        frame = pd.DataFrame([event.model_dump()])

        raw_prediction = int(
            anomaly_model.predict(frame)[0]
        )

        decision_score = float(
            anomaly_model.decision_function(frame)[0]
        )

        is_anomaly = raw_prediction == -1

        return {
            "prediction": (
                "suspicious" if is_anomaly else "normal"
            ),
            "is_anomaly": is_anomaly,
            "decision_score": round(decision_score, 6),
            "message": (
                "Suspicious activity detected."
                if is_anomaly
                else "Activity appears normal."
            ),
        }

    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=f"Prediction failed: {error}",
        )


@app.get("/health")
def health_check():
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1;")

        return {
            "status": "healthy",
            "database": "connected",
            "anomaly_model": (
                "loaded"
                if anomaly_model is not None
                else "unavailable"
            ),
        }

    except Exception as error:
        raise HTTPException(
            status_code=503,
            detail=f"Database unavailable: {error}",
        )


# -------------------------------------------------
# RescueCloud RAG Assistant
# -------------------------------------------------

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import chromadb
from chromadb.utils.embedding_functions import DefaultEmbeddingFunction


RAG_VECTOR_PATH = (
    Path(__file__).resolve().parent
    / "rag"
    / "vector_store"
)

RAG_COLLECTION_NAME = "rescuecloud_knowledge"

OLLAMA_GENERATE_URL = os.getenv(
    "OLLAMA_GENERATE_URL",
    "http://host.docker.internal:11434/api/generate",
)

RAG_MODEL = os.getenv(
    "RAG_MODEL",
    "qwen2.5:0.5b",
)


try:
    rag_client = chromadb.PersistentClient(
        path=str(RAG_VECTOR_PATH)
    )

    rag_collection = rag_client.get_collection(
        name=RAG_COLLECTION_NAME,
        embedding_function=DefaultEmbeddingFunction(),
    )

    rag_error = None

except Exception as error:
    rag_collection = None
    rag_error = str(error)


class RAGQuestion(BaseModel):
    question: str = Field(
        min_length=3,
        max_length=500,
    )


def retrieve_rag_context(
    question: str,
) -> tuple[str, list[str]]:
    if rag_collection is None:
        raise RuntimeError(
            f"Vector database unavailable: {rag_error}"
        )

    results = rag_collection.query(
        query_texts=[question],
        n_results=3,
    )

    documents = results["documents"][0]
    metadatas = results["metadatas"][0]

    context_parts = []
    sources = []

    for document, metadata in zip(
        documents,
        metadatas,
    ):
        source = metadata.get(
            "source",
            "unknown",
        )

        context_parts.append(
            f"Source: {source}\n{document}"
        )

        if source not in sources:
            sources.append(source)

    return "\n\n".join(context_parts), sources


def generate_rag_answer(
    question: str,
    context: str,
) -> str:
    prompt = f"""
You are the RescueCloud project assistant.

Answer only from the supplied RescueCloud context.
Do not invent commands, results, services, or features.

If the answer is unavailable, respond:
"I do not have that information in the RescueCloud knowledge base."

Keep the response clear and concise.

Context:
{context}

Question:
{question}

Answer:
""".strip()

    payload = json.dumps(
        {
            "model": RAG_MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.1,
            },
        }
    ).encode("utf-8")

    request = Request(
        OLLAMA_GENERATE_URL,
        data=payload,
        headers={
            "Content-Type": "application/json"
        },
        method="POST",
    )

    try:
        with urlopen(
            request,
            timeout=120,
        ) as response:
            result = json.loads(
                response.read().decode("utf-8")
            )

    except (HTTPError, URLError) as error:
        raise RuntimeError(
            f"Could not connect to Ollama: {error}"
        ) from error

    return result["response"].strip()


@app.get("/rag/status")
def rag_status():
    return {
        "status": (
            "ready"
            if rag_collection is not None
            else "error"
        ),
        "vector_database_loaded": (
            rag_collection is not None
        ),
        "collection": RAG_COLLECTION_NAME,
        "document_chunks": (
            rag_collection.count()
            if rag_collection is not None
            else 0
        ),
        "model": RAG_MODEL,
        "detail": rag_error,
    }


@app.post("/rag/ask")
def ask_rag(request: RAGQuestion):
    try:
        context, sources = retrieve_rag_context(
            request.question
        )

        answer = generate_rag_answer(
            request.question,
            context,
        )

        return {
            "question": request.question,
            "answer": answer,
            "sources": sources,
            "model": RAG_MODEL,
        }

    except Exception as error:
        raise HTTPException(
            status_code=503,
            detail=f"RAG assistant failed: {error}",
        )
