from __future__ import annotations

import json
import subprocess
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware


PROJECT_DIR = Path(__file__).resolve().parents[1]
RESULTS_DIR = PROJECT_DIR / "results"
STATUS_FILE = RESULTS_DIR / "demo_status.json"
LOG_FILE = RESULTS_DIR / "demo_latest.log"

RESULTS_DIR.mkdir(exist_ok=True)

app = FastAPI(
    title="RescueCloud Recovery Orchestrator",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

state_lock = threading.Lock()

state: dict[str, Any] = {
    "status": "idle",
    "message": "Controlled recovery demo is ready.",
    "started_at": None,
    "finished_at": None,
    "return_code": None,
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def save_state() -> None:
    STATUS_FILE.write_text(
        json.dumps(state, indent=2),
        encoding="utf-8",
    )


def update_state(**values: Any) -> None:
    with state_lock:
        state.update(values)
        save_state()


def log_tail(lines: int = 30) -> list[str]:
    if not LOG_FILE.exists():
        return []

    content = LOG_FILE.read_text(
        encoding="utf-8",
        errors="replace",
    ).splitlines()

    return content[-lines:]


def run_demo() -> None:
    update_state(
        status="checking",
        message="Running system preflight checks.",
        started_at=now_iso(),
        finished_at=None,
        return_code=None,
    )

    try:
        with LOG_FILE.open("w", encoding="utf-8") as log:
            log.write("========== PREFLIGHT CHECK ==========\n")
            log.flush()

            preflight = subprocess.run(
                [
                    "python3",
                    "scripts/preflight_check.py",
                ],
                cwd=PROJECT_DIR,
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
            )

            if preflight.returncode != 0:
                update_state(
                    status="failed",
                    message="Preflight check failed.",
                    finished_at=now_iso(),
                    return_code=preflight.returncode,
                )
                return

            update_state(
                status="running",
                message=(
                    "Attack detection and clean recovery "
                    "experiment is running."
                ),
            )

            log.write(
                "\n========== CONTROLLED RECOVERY ==========\n"
            )
            log.flush()

            experiment = subprocess.run(
                [
                    "python3",
                    "scripts/run_research_experiment.py",
                ],
                cwd=PROJECT_DIR,
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
            )

        if experiment.returncode == 0:
            update_state(
                status="completed",
                message=(
                    "Controlled attack detected and clean "
                    "recovery completed successfully."
                ),
                finished_at=now_iso(),
                return_code=0,
            )
        else:
            update_state(
                status="failed",
                message="Recovery experiment failed.",
                finished_at=now_iso(),
                return_code=experiment.returncode,
            )

    except Exception as error:
        update_state(
            status="failed",
            message=f"Orchestrator error: {error}",
            finished_at=now_iso(),
            return_code=-1,
        )


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "RescueCloud Recovery Orchestrator",
    }


@app.get("/demo/status")
def demo_status() -> dict[str, Any]:
    with state_lock:
        response = dict(state)

    response["log_tail"] = log_tail()
    return response


@app.post("/demo/run")
def start_demo() -> dict[str, Any]:
    with state_lock:
        if state["status"] in {"checking", "running"}:
            raise HTTPException(
                status_code=409,
                detail="A recovery demo is already running.",
            )

        state.update(
            {
                "status": "starting",
                "message": "Starting controlled recovery demo.",
                "started_at": now_iso(),
                "finished_at": None,
                "return_code": None,
            }
        )
        save_state()

    worker = threading.Thread(
        target=run_demo,
        daemon=True,
    )
    worker.start()

    return {
        "status": "starting",
        "message": "Controlled recovery demo started.",
    }
