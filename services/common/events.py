from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class AgentRole(str, Enum):
    SENTINEL = "sentinel"
    AUDITOR = "auditor"
    HEALER = "healer"
    COMMANDER = "commander"


class Channel(str, Enum):
    EHR_AUDIT = "ehr:audit_events"
    THREAT_DETECTED = "threat:detected"
    CONTAINMENT = "threat:containment"
    CANDIDATE_READY = "recovery:candidate_ready"
    RECOVERY_TRIGGER = "recovery:trigger"
    RECOVERY_COMPLETED = "recovery:completed"
    AGENT_STATUS = "agent:status"
    HEALTH_CHECK = "agent:health_check"  # periodic liveness ping between agents


class HealthCheckEvent(BaseModel):
    """Periodic liveness ping emitted by each agent to the commander."""
    agent_id: str
    role: str
    timestamp: str = Field(default_factory=now_utc_iso)
    status: str = "healthy"          # healthy | degraded | unreachable
    uptime_seconds: Optional[float] = None
    last_event_processed: Optional[str] = None


class AuditEvent(BaseModel):
    """Emitted by EHR service on every data modification or access."""
    event_id: str
    timestamp: str = Field(default_factory=now_utc_iso)
    method: str
    path: str
    client_ip: str
    user_id: Optional[str] = None
    action_type: str = "query"  # query, insert, update, delete, bulk_export
    payload_summary: Dict[str, Any] = Field(default_factory=dict)
    entropy_score: Optional[float] = None


class ThreatDetectedEvent(BaseModel):
    """Emitted by Threat Sentinel Agent when an anomaly/attack pattern is caught."""
    event_id: str
    timestamp: str = Field(default_factory=now_utc_iso)
    threat_type: str = "ransomware_mutation"
    confidence_score: float
    anomaly_score: float
    compromise_time: str
    attacker_ip: str
    blast_radius: Dict[str, Any] = Field(default_factory=dict)
    suggested_action: str = "airgap_and_pitr"
    reason: str


class ContainmentEvent(BaseModel):
    """Emitted when circuit-breaker air-gap containment triggers."""
    event_id: str
    timestamp: str = Field(default_factory=now_utc_iso)
    blocked_ips: List[str] = Field(default_factory=list)
    read_only_mode: bool = True
    wal_switched: bool = True
    reaction_time_ms: float = 38.0
    reason: str


class CandidateBackupEvent(BaseModel):
    """Emitted by Blockchain Auditor Agent identifying clean pre-attack backup."""
    event_id: str
    timestamp: str = Field(default_factory=now_utc_iso)
    compromise_time: str
    clean_target_time: str
    base_backup_file: str
    sha256_hash: str
    onchain_ledger_verified: bool
    rpo_estimate_seconds: float = 0.0
    notes: str = "Base backup integrity cryptographically verified on-chain."


class RecoveryTriggerEvent(BaseModel):
    """Emitted to trigger automated or supervised PITR recovery."""
    event_id: str
    timestamp: str = Field(default_factory=now_utc_iso)
    target_recovery_time: str
    dry_run: bool = False
    requested_by: str = "autonomous_healer"


class RecoveryCompletedEvent(BaseModel):
    """Emitted by PITR Healer Agent once recovery DB is promoted."""
    event_id: str
    timestamp: str = Field(default_factory=now_utc_iso)
    status: str = "success"
    compromise_time: str
    target_recovery_time: str
    restored_base_backup: str
    wal_segments_replayed: int = 1
    rpo_gap_achieved: str = "0.0s (ZERO DATA LOSS — WAL PITR)"
    recovery_api_url: str = "http://localhost:8002"
    verification_passed: bool = True
    message: str


class AgentHeartbeat(BaseModel):
    """Emitted periodically by each autonomous agent to report health and tasks."""
    agent_name: str
    role: AgentRole
    status: str = "healthy"  # healthy, defending, recovering, idle
    current_task: Optional[str] = None
    metrics: Dict[str, Any] = Field(default_factory=dict)
    timestamp: str = Field(default_factory=now_utc_iso)


# ---------------------------------------------------------------------------
# Event versioning
# ---------------------------------------------------------------------------
# All event models should include a 'version' field when the schema changes.
# Consumers must handle unknown fields gracefully (Pydantic ignores extras
# by default when using model_validate — do not set model_config to 'forbid').


# ---------------------------------------------------------------------------
# Channel subscription guide
# ---------------------------------------------------------------------------
# Sentinel subscribes to: Channel.EHR_AUDIT
# Auditor subscribes to:  Channel.THREAT_DETECTED
# Healer subscribes to:   Channel.CANDIDATE_READY
# Gateway subscribes to:  Channel.RECOVERY_COMPLETED, Channel.AGENT_STATUS
# All agents subscribe to: Channel.HEALTH_CHECK


# ---------------------------------------------------------------------------
# Event retention
# ---------------------------------------------------------------------------
# Redis pub/sub does not persist events — if a subscriber is offline when
# an event is published, it misses the event. For guaranteed delivery,
# consider using Redis Streams instead of pub/sub in a future iteration.
# Current design accepts at-most-once delivery for non-critical status events.


# ---------------------------------------------------------------------------
# Adding new event types
# ---------------------------------------------------------------------------
# To add a new event type:
#   1. Add a new Channel enum value (Channel.NEW_EVENT = 'namespace:event_name')
#   2. Create a Pydantic model class inheriting from BaseModel
#   3. Update AGENTS.md in blockchain/ with the new channel description
#   4. Update the channel subscription map comment at the bottom of this file


# ---------------------------------------------------------------------------
# Cross-service compatibility
# ---------------------------------------------------------------------------
# All services in this system use the same event models from this module.
# If you fork or extend RescueCloud for a different hospital:
#   1. Keep this module as the single source of truth for event schemas
#   2. Bump the package version when making breaking schema changes
#   3. Deploy all services simultaneously when changing event schemas
#      to avoid version skew between producer and consumer.
