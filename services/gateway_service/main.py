from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request as URLRequest, urlopen

import httpx
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Add parent directory to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from services.common.bus import get_event_bus
from services.common.events import Channel

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [Gateway-Commander] %(message)s",
)
logger = logging.getLogger("rescuecloud.gateway")

app = FastAPI(title="RescueCloud API Gateway & Incident Commander", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Service URLs from environment (supporting docker container hosts or local host)
EHR_SERVICE_URL = os.getenv("EHR_SERVICE_URL", "http://localhost:8010")
SENTINEL_SERVICE_URL = os.getenv("SENTINEL_SERVICE_URL", "http://localhost:8020")
AUDITOR_SERVICE_URL = os.getenv("AUDITOR_SERVICE_URL", "http://localhost:8030")
HEALER_SERVICE_URL = os.getenv("HEALER_SERVICE_URL", "http://localhost:8040")

event_bus = get_event_bus()

# Multi-Agent Incident Commander Telemetry
_AGENT_STATUSES: Dict[str, Any] = {
    "sentinel": {
        "name": "Threat Sentinel Agent",
        "role": "Detection & Air-Gap Containment",
        "status": "active",
        "service_url": SENTINEL_SERVICE_URL,
        "last_action": "Monitoring real-time audit event stream",
    },
    "auditor": {
        "name": "Blockchain Auditor Agent",
        "role": "Cryptographic Integrity & On-Chain Ledger",
        "status": "active",
        "service_url": AUDITOR_SERVICE_URL,
        "last_action": "Synchronized with smart contract BackupLedger",
    },
    "healer": {
        "name": "PITR Healer Agent",
        "role": "Zero-RPO Point-In-Time Recovery Replay",
        "status": "standby",
        "service_url": HEALER_SERVICE_URL,
        "last_action": "WAL replay engine armed for recovery target",
    },
    "commander": {
        "name": "Incident Commander Agent",
        "role": "Multi-Agent Coordination & SOC Advisory",
        "status": "active",
        "service_url": "http://localhost:8001",
        "last_action": "Gateway routing and event mesh operating normally",
    },
}

_RECENT_EVENTS: List[Dict[str, Any]] = []


def on_agent_event(event_dict: Dict[str, Any]):
    event_dict["received_at"] = datetime.now(timezone.utc).isoformat()
    _RECENT_EVENTS.append(event_dict)
    if len(_RECENT_EVENTS) > 100:
        _RECENT_EVENTS.pop(0)


# Subscribe Commander to all key agent channels
event_bus.subscribe([Channel.THREAT_DETECTED, Channel.CONTAINMENT, Channel.CANDIDATE_READY, Channel.RECOVERY_COMPLETED], on_agent_event)


# ---------------------------------------------------------------------------
# RAG Configuration
# ---------------------------------------------------------------------------
PROJECT_DIR = Path(__file__).resolve().parents[2]
VECTOR_DIR = PROJECT_DIR / "rag" / "vector_store"
RAG_COLLECTION_NAME = "rescuecloud_knowledge"
RAG_MODEL = "qwen2.5:0.5b"
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")

rag_collection = None
rag_error = None
try:
    import chromadb
    from chromadb.utils.embedding_functions import DefaultEmbeddingFunction

    if VECTOR_DIR.exists():
        client = chromadb.PersistentClient(path=str(VECTOR_DIR))
        rag_collection = client.get_collection(
            name=RAG_COLLECTION_NAME,
            embedding_function=DefaultEmbeddingFunction(),
        )
        logger.info(f"Loaded RAG Chroma collection '{RAG_COLLECTION_NAME}'")
    else:
        rag_error = f"Vector directory not found: {VECTOR_DIR}"
except Exception as exc:
    rag_error = str(exc)


class RAGQuestion(BaseModel):
    question: str


# ---------------------------------------------------------------------------
# Proxy helper
# ---------------------------------------------------------------------------
async def proxy_request(target_base: str, path: str, request: Request) -> Response:
    url = f"{target_base.rstrip('/')}/{path.lstrip('/')}"
    if request.url.query:
        url = f"{url}?{request.url.query}"

    body = await request.body()
    headers = dict(request.headers)
    headers.pop("host", None)
    headers.pop("content-length", None)

    async with httpx.AsyncClient(timeout=45.0) as client:
        try:
            resp = await client.request(
                method=request.method,
                url=url,
                headers=headers,
                content=body,
            )
            return Response(
                content=resp.content,
                status_code=resp.status_code,
                headers=dict(resp.headers),
                media_type=resp.headers.get("content-type"),
            )
        except httpx.RequestError as err:
            logger.error(f"Proxy error connecting to {url}: {err}")
            return Response(
                content=json.dumps({"detail": f"Downstream microservice unavailable: {err}"}),
                status_code=503,
                media_type="application/json",
            )


# ---------------------------------------------------------------------------
# Gateway Routing
# ---------------------------------------------------------------------------
@app.get("/")
def root():
    return {
        "service": "RescueCloud API Gateway & Incident Commander",
        "version": "2.0.0",
        "architecture": "Event-Driven Microservices with Autonomous Multi-Agent Response",
        "agents": list(_AGENT_STATUSES.keys()),
    }


@app.get("/health")
async def aggregated_health():
    statuses = {}
    async with httpx.AsyncClient(timeout=3.0) as client:
        for name, base_url in [
            ("ehr", EHR_SERVICE_URL),
            ("sentinel", SENTINEL_SERVICE_URL),
            ("auditor", AUDITOR_SERVICE_URL),
            ("healer", HEALER_SERVICE_URL),
        ]:
            try:
                r = await client.get(f"{base_url}/health")
                statuses[name] = r.json() if r.status_code == 200 else {"status": "unhealthy", "code": r.status_code}
            except Exception as e:
                statuses[name] = {"status": "down", "error": str(e)}

    all_ok = all(v.get("status") in {"healthy", "nominal"} for v in statuses.values())
    return {
        "status": "healthy" if all_ok else "degraded",
        "gateway": "online",
        "commander_agent": "ready",
        "microservices": statuses,
    }


@app.get("/agents/status")
def get_agents_status():
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "agents": _AGENT_STATUSES,
        "recent_incident_events": _RECENT_EVENTS[-15:],
    }


# Route: /patients -> EHR Service
@app.api_route("/patients{rest_of_path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def route_patients(rest_of_path: str, request: Request):
    return await proxy_request(EHR_SERVICE_URL, f"/patients{rest_of_path}", request)


# Route: /anomaly -> Sentinel Service
@app.api_route("/anomaly{rest_of_path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def route_anomaly(rest_of_path: str, request: Request):
    return await proxy_request(SENTINEL_SERVICE_URL, f"/anomaly{rest_of_path}", request)


# Route: /backups -> Auditor Service
@app.api_route("/backups{rest_of_path:path}", methods=["GET", "POST"])
async def route_backups(rest_of_path: str, request: Request):
    return await proxy_request(AUDITOR_SERVICE_URL, f"/backups{rest_of_path}", request)


# Route: /incidents -> Healer Service
@app.api_route("/incidents{rest_of_path:path}", methods=["GET", "POST"])
async def route_incidents(rest_of_path: str, request: Request):
    return await proxy_request(HEALER_SERVICE_URL, f"/incidents{rest_of_path}", request)


# ---------------------------------------------------------------------------
# RAG Endpoints
# ---------------------------------------------------------------------------
@app.get("/rag/status")
def rag_status():
    return {
        "status": "ready" if rag_collection is not None else "error",
        "vector_database_loaded": rag_collection is not None,
        "collection": RAG_COLLECTION_NAME,
        "document_chunks": rag_collection.count() if rag_collection is not None else 0,
        "model": RAG_MODEL,
        "detail": rag_error,
    }


@app.post("/rag/ask")
def ask_rag(request: RAGQuestion):
    if rag_collection is None:
        return {
            "question": request.question,
            "answer": "RescueCloud Incident Commander RAG knowledge base is initializing.",
            "sources": [],
            "model": RAG_MODEL,
        }

    try:
        results = rag_collection.query(
            query_texts=[request.question],
            n_results=3,
        )
        documents = results["documents"][0] if results["documents"] else []
        metadatas = results["metadatas"][0] if results["metadatas"] else []

        context_parts = []
        sources = []
        for doc, meta in zip(documents, metadatas):
            src = meta.get("source", "knowledge_base")
            context_parts.append(f"Source: {src}\n{doc}")
            if src not in sources:
                sources.append(src)

        context = "\n\n".join(context_parts)

        # Attempt Ollama answer generation or provide structured context
        answer = f"RescueCloud Autonomous Incident Commander Guidance:\n\n{context[:600]}"
        try:
            payload = json.dumps({
                "model": RAG_MODEL,
                "prompt": f"You are the RescueCloud Incident Commander. Context:\n{context}\n\nQuestion: {request.question}\nAnswer:",
                "stream": False,
            }).encode("utf-8")
            url_req = URLRequest(OLLAMA_URL, data=payload, headers={"Content-Type": "application/json"}, method="POST")
            with urlopen(url_req, timeout=10) as resp:
                res_data = json.loads(resp.read().decode("utf-8"))
                answer = res_data["response"].strip()
        except Exception:
            pass  # Fall back to context guidance

        return {
            "question": request.question,
            "answer": answer,
            "sources": sources,
            "model": RAG_MODEL,
        }
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8001")))
