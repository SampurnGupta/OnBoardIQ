"""Blackboard Service — FastAPI app.

Zoned, versioned, append-only shared state with access control by agent_id.
"""

from __future__ import annotations

import os
import uuid
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Header, HTTPException, status
from pydantic import BaseModel, Field

from onboardiq.blackboard.store import (
    BlackboardStore,
    RunNotFoundError,
    SQLiteBlackboardStore,
    VersionMismatchError,
)
from onboardiq.schema import (
    Blackboard,
    GuardrailEvent,
)

app = FastAPI(title="OnboardIQ Blackboard Service", version="0.1.0")

# Access control matrix per docs/03_ARCHITECTURE.md Section 3
ALL_EXCEPT_PII_VAULT = {"intake", "verification", "screening", "risk", "review", "system"}

ZONE_READ_PERMISSIONS: dict[str, set[str]] = {
    "adk.gateway": {"intake", "pii_vault", "system"},
    "adk.orchestrator": ALL_EXCEPT_PII_VAULT,
    "adk.extractor": {"intake", "pii_vault"},
    "crewai.identity_verifier": {"intake", "verification", "pii_vault"},
    "crewai.sanctions_screener": {"intake"},
    "crewai.media_analyst": {"intake"},
    "crewai.ubo_analyst": {"intake", "verification"},
    "adk.risk_scorer": ALL_EXCEPT_PII_VAULT,
    "adk.reviewer": ALL_EXCEPT_PII_VAULT,
    "adk.comms": {"intake", "review", "system"},
    "telemetry": {"system"},
    # Privileged administrative agents / tests
    "admin": ALL_EXCEPT_PII_VAULT | {"pii_vault"},
    "system.init": ALL_EXCEPT_PII_VAULT | {"pii_vault"},
}

ZONE_WRITE_PERMISSIONS: dict[str, set[str]] = {
    "adk.gateway": {"intake", "pii_vault", "system"},
    "adk.orchestrator": {"risk", "review", "system"},
    "adk.extractor": {"verification", "intake"},
    "crewai.identity_verifier": {"verification"},
    "crewai.sanctions_screener": {"screening"},
    "crewai.media_analyst": {"screening"},
    "crewai.ubo_analyst": {"screening"},
    "adk.risk_scorer": {"risk"},
    "adk.reviewer": {"review"},
    "adk.comms": {"system"},
    "telemetry": {"system"},
    # Privileged administrative agents / tests
    "admin": ALL_EXCEPT_PII_VAULT | {"pii_vault"},
    "system.init": ALL_EXCEPT_PII_VAULT | {"pii_vault"},
}


def get_store() -> BlackboardStore:
    db_path = os.getenv("BLACKBOARD_DB_PATH", ":memory:")
    # If using memory store across multiple requests in the app lifecycle, attach to app.state
    if not hasattr(app.state, "store"):
        app.state.store = SQLiteBlackboardStore(db_path=db_path)
    return app.state.store


def get_agent_id(
    x_agent_id: Annotated[str | None, Header(alias="X-Agent-ID")] = None,
) -> str:
    if not x_agent_id:
        return "admin"
    return x_agent_id


StoreDep = Annotated[BlackboardStore, Depends(get_store)]
AgentIdDep = Annotated[str, Depends(get_agent_id)]


class EventWriteRequest(BaseModel):
    agent_id: str | None = None
    zone: str
    op: str = "update"  # replace, update, append
    payload: dict[str, Any]
    expected_version: int = Field(ge=0)


@app.get("/")
def root_info() -> dict[str, str]:
    return {
        "service": "OnboardIQ Blackboard Service",
        "status": "running",
        "docs_url": "/docs",
    }


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/runs", response_model=Blackboard, status_code=status.HTTP_201_CREATED)
def create_run(
    board: Blackboard,
    store: StoreDep,
) -> Blackboard:
    return store.create_run(board)


@app.get("/runs/{run_id}", response_model=Blackboard)
def get_run(
    run_id: str,
    agent_id: AgentIdDep,
    store: StoreDep,
) -> Blackboard:
    board = store.get_run(run_id)
    if not board:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")

    allowed_reads = ZONE_READ_PERMISSIONS.get(agent_id, set())
    if "pii_vault" not in allowed_reads:
        # Mask out pii_vault contents if the caller is not privileged
        board.pii_vault.raw_name = "***"
        board.pii_vault.address = "***"
        board.pii_vault.dob = None
        board.pii_vault.id_numbers = {}
        board.pii_vault.raw_document_text = {}

    return board


@app.get("/runs/{run_id}/zones/{zone}")
def get_zone(
    run_id: str,
    zone: str,
    agent_id: AgentIdDep,
    store: StoreDep,
) -> Any:
    allowed_reads = ZONE_READ_PERMISSIONS.get(agent_id, set())
    if zone not in allowed_reads:
        event = GuardrailEvent(
            event_id=str(uuid.uuid4()),
            stage="blackboard_access",
            category="access_denied",
            action="blocked",
            agent_id=agent_id,
            score=1.0,
            detail=f"Agent '{agent_id}' denied read access to zone '{zone}'",
        )
        store.append_guardrail_event(run_id, event)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Agent '{agent_id}' is not authorized to read zone '{zone}'",
        )

    board = store.get_run(run_id)
    if not board:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")

    zone_data = getattr(board, zone, None)
    if zone_data is None:
        raise HTTPException(status_code=404, detail=f"Zone '{zone}' not found")

    return zone_data


@app.post("/runs/{run_id}/events")
def append_event(
    run_id: str,
    req: EventWriteRequest,
    agent_id_header: AgentIdDep,
    store: StoreDep,
) -> dict[str, Any]:
    active_agent_id = req.agent_id or agent_id_header
    allowed_writes = ZONE_WRITE_PERMISSIONS.get(active_agent_id, set())

    if req.zone not in allowed_writes:
        event = GuardrailEvent(
            event_id=str(uuid.uuid4()),
            stage="blackboard_access",
            category="access_denied",
            action="blocked",
            agent_id=active_agent_id,
            score=1.0,
            detail=f"Agent '{active_agent_id}' denied write access to zone '{req.zone}'",
        )
        store.append_guardrail_event(run_id, event)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Agent '{active_agent_id}' is not authorized to write to zone '{req.zone}'",
        )

    try:
        updated_board, event_record = store.apply_event(
            run_id=run_id,
            agent_id=active_agent_id,
            zone=req.zone,
            op=req.op,
            payload=req.payload,
            expected_version=req.expected_version,
        )
        return {
            "status": "applied",
            "version": updated_board.version,
            "event": event_record,
        }
    except RunNotFoundError:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    except VersionMismatchError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )


@app.get("/runs/{run_id}/events")
def get_events(
    run_id: str,
    store: StoreDep,
) -> list[dict[str, Any]]:
    return store.get_events(run_id)
