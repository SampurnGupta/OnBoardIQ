"""Telemetry callbacks and trace logging for OnboardIQ.

Per docs/06_IMPLEMENTATION_PLAN.md T12:
- ADK callbacks and CrewAI step/task callbacks emit StepTrace records.
- Records agent_id, framework, phase, step_type, name, latency, tokens, cost, error.
- Writes traces to the blackboard 'system' zone.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any, Literal

from onboardiq.blackboard.client import BlackboardClient
from onboardiq.schema import Phase, StepTrace
from onboardiq.telemetry.cost import estimate_cost


def create_step_trace(
    agent_id: str,
    phase: Phase | str,
    step_type: Literal["model", "tool", "guardrail", "a2a", "blackboard"],
    name: str,
    latency_ms: float,
    trace_id: str | None = None,
    framework: Literal["crewai", "adk"] | None = None,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    cost_usd: float = 0.0,
    error: str | None = None,
) -> StepTrace:
    """Construct a validated StepTrace object."""
    phase_enum = Phase(phase) if isinstance(phase, str) else phase
    fw: Literal["crewai", "adk"] = framework or ("crewai" if "crewai" in agent_id else "adk")
    tid = trace_id or f"tr_{uuid.uuid4().hex[:8]}"

    # Auto-estimate cost if not explicitly provided
    if cost_usd == 0.0 and (prompt_tokens > 0 or completion_tokens > 0):
        cost_usd = estimate_cost("default", prompt_tokens, completion_tokens)

    return StepTrace(
        trace_id=tid,
        agent_id=agent_id,
        framework=fw,
        phase=phase_enum,
        step_type=step_type,
        name=name,
        latency_ms=round(latency_ms, 2),
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cost_usd=round(cost_usd, 6),
        error=error,
    )


def record_step_trace(
    board_client: BlackboardClient,
    run_id: str,
    agent_id: str,
    phase: Phase | str,
    step_type: Literal["model", "tool", "guardrail", "a2a", "blackboard"],
    name: str,
    latency_ms: float,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    model_name: str = "default",
    current_version: int = 0,
    error: str | None = None,
) -> tuple[StepTrace, int]:
    """Emit and append a StepTrace to the blackboard's system zone."""
    cost = estimate_cost(model_name, prompt_tokens, completion_tokens)
    trace = create_step_trace(
        agent_id=agent_id,
        phase=phase,
        step_type=step_type,
        name=name,
        latency_ms=latency_ms,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cost_usd=cost,
        error=error,
    )

    try:
        board_client.append_event(
            run_id=run_id,
            zone="system",
            payload={"field": "traces", "item": trace.model_dump(mode="json")},
            expected_version=current_version,
            op="append",
            agent_id="telemetry",
        )
        return trace, current_version + 1
    except Exception:  # noqa: BLE001
        # Retry with latest version
        try:
            latest = board_client.get_run(run_id, agent_id="telemetry")
            board_client.append_event(
                run_id=run_id,
                zone="system",
                payload={"field": "traces", "item": trace.model_dump(mode="json")},
                expected_version=latest.version,
                op="append",
                agent_id="telemetry",
            )
            return trace, latest.version + 1
        except Exception:  # noqa: BLE001
            return trace, current_version


@contextmanager
def trace_step(
    board_client: BlackboardClient,
    run_id: str,
    agent_id: str,
    phase: Phase | str,
    step_type: Literal["model", "tool", "guardrail", "a2a", "blackboard"],
    name: str,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    model_name: str = "default",
) -> Generator[dict[str, Any], None, None]:
    """Context manager to measure latency and record a StepTrace to the blackboard."""
    start = time.perf_counter()
    ctx: dict[str, Any] = {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "error": None,
    }
    try:
        yield ctx
    except Exception as exc:
        ctx["error"] = str(exc)
        raise
    finally:
        latency_ms = (time.perf_counter() - start) * 1000.0
        p_tokens = ctx.get("prompt_tokens", prompt_tokens)
        c_tokens = ctx.get("completion_tokens", completion_tokens)
        cost = estimate_cost(model_name, p_tokens, c_tokens)
        trace = create_step_trace(
            agent_id=agent_id,
            phase=phase,
            step_type=step_type,
            name=name,
            latency_ms=latency_ms,
            prompt_tokens=p_tokens,
            completion_tokens=c_tokens,
            cost_usd=cost,
            error=ctx.get("error"),
        )
        try:
            latest = board_client.get_run(run_id, agent_id="telemetry")
            board_client.append_event(
                run_id=run_id,
                zone="system",
                payload={"field": "traces", "item": trace.model_dump(mode="json")},
                expected_version=latest.version,
                op="append",
                agent_id="telemetry",
            )
        except Exception:  # noqa: BLE001, S110
            pass
