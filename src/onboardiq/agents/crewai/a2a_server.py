"""A2A (Agent-to-Agent) service wrapper for CrewAI Screening Crew.

Publishes an Agent Card adhering to the A2A discovery standard and provides
an RPC endpoint for the ADK orchestrator to trigger screening remotely.
"""

from __future__ import annotations

import time
import uuid
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from onboardiq.agents.crewai.screening_crew import ScreeningCrew
from onboardiq.blackboard.client import BlackboardClient
from onboardiq.schema import Phase, StepTrace
from onboardiq.telemetry.tracing import extract_trace_context, inject_trace_context, trace_agent

app = FastAPI(title="OnboardIQ CrewAI A2A Screening Service", version="0.1.0")
a2a_app = app  # Alias for convenient uvicorn invocation (uvicorn ...a2a_server:a2a_app)


class SkillParameter(BaseModel):
    name: str
    type: str
    description: str
    required: bool = True


class AgentSkill(BaseModel):
    name: str
    description: str
    parameters: list[SkillParameter]
    output_schema: str


class AgentCard(BaseModel):
    name: str = "crewai-screening-crew"
    version: str = "1.0.0"
    protocol_version: str = "0.2"
    framework: str = "CrewAI"
    description: str = (
        "Multi-agent screening crew providing registry lookup, identity cross-checking, "
        "and fuzzy sanctions/PEP screening with evidence trails."
    )
    capabilities: list[str] = [
        "identity_verification",
        "sanctions_screening",
        "pep_screening",
    ]
    skills: list[AgentSkill] = [
        AgentSkill(
            name="screen_client",
            description="Executes identity verification and sanctions screening against the active blackboard.",
            parameters=[
                SkillParameter(name="run_id", type="string", description="Active Blackboard run ID"),
                SkillParameter(name="current_version", type="integer", description="Expected blackboard concurrency version"),
            ],
            output_schema="ScreeningResult",
        )
    ]
    endpoint_url: str = "/a2a/screening"


AGENT_CARD = AgentCard()


class A2AScreeningRequest(BaseModel):
    run_id: str
    current_version: int = Field(ge=0)
    agent_id: str = "adk.orchestrator"


class A2AScreeningResponse(BaseModel):
    status: str
    run_id: str
    checks_count: int
    hits_count: int
    red_flags_count: int
    new_version: int
    artifacts: dict[str, Any] = Field(default_factory=dict)


@app.get("/.well-known/agent.json", response_model=AgentCard)
@app.get("/agent-card.json", response_model=AgentCard)
def get_agent_card() -> AgentCard:
    """Return published A2A Agent Card for agent discovery."""
    return AGENT_CARD


def get_board_client(agent_id: str = "adk.orchestrator") -> BlackboardClient:
    if hasattr(app.state, "board_client") and app.state.board_client is not None:
        return app.state.board_client
    return BlackboardClient(agent_id=agent_id)


@app.post("/a2a/screening", response_model=A2AScreeningResponse)
def handle_screening_call(req: A2AScreeningRequest, request: Request) -> A2AScreeningResponse:
    """A2A RPC endpoint invoked by ADK Orchestrator to dispatch screening."""
    board_client = get_board_client(agent_id=req.agent_id)
    crew = ScreeningCrew()

    headers = dict(request.headers) if request is not None else {}
    _ = extract_trace_context(headers)

    try:
        with trace_agent("crewai.screening_crew", "screening", run_id=req.run_id):
            checks, hits, flags, new_ver = crew.run_screening(
                run_id=req.run_id,
                board_client=board_client,
                current_version=req.current_version,
            )
        return A2AScreeningResponse(
            status="success",
            run_id=req.run_id,
            checks_count=len(checks),
            hits_count=len(hits),
            red_flags_count=len(flags),
            new_version=new_ver,
            artifacts={
                "checks": [c.model_dump(mode="json") for c in checks],
                "hits": [h.model_dump(mode="json") for h in hits],
                "red_flags": [f.model_dump(mode="json") for f in flags],
            },
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"A2A Screening execution failed: {e}") from e


def invoke_a2a_screening(
    run_id: str,
    current_version: int,
    a2a_url: str = "http://localhost:8003",
    board_client: BlackboardClient | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> tuple[A2AScreeningResponse, int]:
    """Client function used by ADK Orchestrator to trigger screening over A2A protocol.

    Measures latency and records a StepTrace of type 'a2a' to the blackboard system zone.
    """
    start_time = time.perf_counter()
    error_msg = None
    res = None
    new_version = current_version

    # Inject trace context into headers
    req_headers: dict[str, str] = {}
    inject_trace_context(req_headers)

    # If app passed directly for in-memory testing or transport
    if transport is not None:
        from starlette.testclient import TestClient

        client = TestClient(app)
        resp = client.post(
            "/a2a/screening",
            json={"run_id": run_id, "current_version": current_version, "agent_id": "adk.orchestrator"},
            headers=req_headers,
        )
        resp.raise_for_status()
        res = A2AScreeningResponse.model_validate(resp.json())
        new_version = res.new_version
    else:
        with httpx.Client(base_url=a2a_url.rstrip("/"), timeout=20.0) as client:
            resp = client.post(
                "/a2a/screening",
                json={"run_id": run_id, "current_version": current_version, "agent_id": "adk.orchestrator"},
                headers=req_headers,
            )
            resp.raise_for_status()
            res = A2AScreeningResponse.model_validate(resp.json())
            new_version = res.new_version

    elapsed_ms = (time.perf_counter() - start_time) * 1000.0

    # Log StepTrace to system zone per architecture §10 and criterion 5
    if board_client is not None:
        trace = StepTrace(
            trace_id=str(uuid.uuid4()),
            agent_id="adk.orchestrator",
            framework="adk",
            phase=Phase.SCREENING,
            step_type="a2a",
            name="crewai_screening_a2a_call",
            latency_ms=round(elapsed_ms, 2),
            prompt_tokens=0,
            completion_tokens=0,
            cost_usd=0.0,
            error=error_msg,
        )
        board_client.append_event(
            run_id=run_id,
            zone="system",
            payload={"field": "traces", "item": trace.model_dump(mode="json")},
            expected_version=new_version,
            op="append",
            agent_id="adk.orchestrator",
        )
        new_version += 1

    return res, new_version
