"""FastMCP tool server for OnboardIQ.

Hosts external capabilities and exposes them over MCP to both CrewAI and Google ADK.
"""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from onboardiq.mcp_server.tools.blackboard_tools import (
    read_blackboard,
    write_blackboard,
)
from onboardiq.mcp_server.tools.doc_ocr import DocOcrOutput, extract_doc_ocr
from onboardiq.mcp_server.tools.registry_lookup import (
    RegistryLookupOutput,
    lookup_registry,
)
from onboardiq.mcp_server.tools.risk_predict import (
    RiskModelOutput,
    predict_case_risk,
)
from onboardiq.mcp_server.tools.sanctions_screen import (
    SanctionsScreenOutput,
    screen_sanctions,
)
from onboardiq.mcp_server.tools.ubo_graph import UBOResult, resolve_ubo_graph

mcp = FastMCP("OnboardIQ Tool Server")


@mcp.tool(name="registry_lookup")
def tool_registry_lookup(id_number: str) -> dict[str, Any]:
    """Look up an ID number (PAN, Passport, CIN) in the mock government registry."""
    res: RegistryLookupOutput = lookup_registry(id_number=id_number)
    return res.model_dump()


@mcp.tool(name="sanctions_screen")
def tool_sanctions_screen(
    name: str,
    country: str | None = None,
    threshold: float = 0.65,
) -> dict[str, Any]:
    """Screen an individual or company name against sanctions and PEP lists."""
    res: SanctionsScreenOutput = screen_sanctions(
        name=name, country=country, threshold=threshold
    )
    return res.model_dump()


@mcp.tool(name="doc_ocr")
def tool_doc_ocr(doc_path: str) -> dict[str, Any]:
    """Extract text, fields, and tamper score from an uploaded document image or PDF."""
    res: DocOcrOutput = extract_doc_ocr(doc_path=doc_path)
    return res.model_dump()


@mcp.tool(name="risk_model_predict")
def tool_risk_model_predict(
    country_risk: float = 0.1,
    occupation_risk: float = 0.1,
    monthly_volume_inr: float = 50000.0,
    num_red_flags: int = 0,
    max_screening_score: float = 0.0,
    tamper_score: float = 0.0,
    is_company: bool = False,
) -> dict[str, Any]:
    """Predict applicant high risk probability using trained ML gradient boosting model."""
    res: RiskModelOutput = predict_case_risk(
        country_risk=country_risk,
        occupation_risk=occupation_risk,
        monthly_volume_inr=monthly_volume_inr,
        num_red_flags=num_red_flags,
        max_screening_score=max_screening_score,
        tamper_score=tamper_score,
        is_company=is_company,
    )
    return res.model_dump()


@mcp.tool(name="blackboard_read")
def tool_blackboard_read(
    run_id: str,
    zone: str,
    agent_id: str = "admin",
) -> Any:
    """Read a specific zone from the shared Blackboard."""
    return read_blackboard(run_id=run_id, zone=zone, agent_id=agent_id)


@mcp.tool(name="blackboard_write")
def tool_blackboard_write(
    run_id: str,
    zone: str,
    payload: dict[str, Any],
    expected_version: int,
    op: str = "update",
    agent_id: str = "admin",
) -> dict[str, Any]:
    """Atomically append an event to update a Blackboard zone."""
    return write_blackboard(
        run_id=run_id,
        zone=zone,
        payload=payload,
        expected_version=expected_version,
        op=op,
        agent_id=agent_id,
    )


@mcp.tool(name="ubo_graph")
def tool_ubo_graph(
    ownership_chart: dict[str, Any],
    threshold_pct: float = 10.0,
) -> dict[str, Any]:
    """Trace corporate ownership network and resolve beneficial owners above threshold."""
    res: UBOResult = resolve_ubo_graph(ownership_chart=ownership_chart, threshold_pct=threshold_pct)
    return res.model_dump()


if __name__ == "__main__":
    mcp.run()
