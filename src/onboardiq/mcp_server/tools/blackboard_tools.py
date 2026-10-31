"""Blackboard tools exposed via FastMCP.

Enables agents in both CrewAI and Google ADK to read from and write to
the shared Blackboard Service through standard MCP tool invocations.
"""

from __future__ import annotations

import os
from typing import Any

from pydantic import BaseModel, Field

from onboardiq.blackboard.client import BlackboardClient


class BlackboardReadInput(BaseModel):
    run_id: str = Field(description="Active run identifier")
    zone: str = Field(description="Blackboard zone to read (e.g., intake, verification, screening)")
    agent_id: str = Field(default="admin", description="Calling agent identifier for access control")


class BlackboardWriteInput(BaseModel):
    run_id: str = Field(description="Active run identifier")
    zone: str = Field(description="Blackboard zone to write to")
    payload: dict[str, Any] = Field(description="Payload to apply to the zone")
    expected_version: int = Field(ge=0, description="Optimistic concurrency expected version")
    op: str = Field(default="update", description="Operation: replace, update, or append")
    agent_id: str = Field(default="admin", description="Calling agent identifier")


def _get_client() -> BlackboardClient:
    base_url = os.getenv("BLACKBOARD_URL", "http://localhost:8001")
    token = os.getenv("BLACKBOARD_TOKEN")
    return BlackboardClient(base_url=base_url, service_token=token)


def read_blackboard(run_id: str, zone: str, agent_id: str = "admin") -> Any:
    """Read a zone from the Blackboard service."""
    client = _get_client()
    return client.get_zone(run_id=run_id, zone=zone, agent_id=agent_id)


def write_blackboard(
    run_id: str,
    zone: str,
    payload: dict[str, Any],
    expected_version: int,
    op: str = "update",
    agent_id: str = "admin",
) -> dict[str, Any]:
    """Write an event to update a Blackboard zone with optimistic concurrency."""
    client = _get_client()
    return client.append_event(
        run_id=run_id,
        zone=zone,
        payload=payload,
        expected_version=expected_version,
        op=op,
        agent_id=agent_id,
    )

