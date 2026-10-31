"""Tests for Task T29: OpenTelemetry tracing, provenance verification, and A2A context propagation."""

from __future__ import annotations

import json
from pathlib import Path

from onboardiq.agents.adk.orchestrator import Orchestrator
from onboardiq.blackboard.client import BlackboardClient
from onboardiq.schema import (
    GuardrailEvent,
    LabelledCase,
    Mode,
    Pattern,
    Persona,
    Reasoning,
    RunConfig,
)
from onboardiq.telemetry.tracing import (
    clear_spans,
    extract_trace_context,
    get_finished_spans,
    get_provenance_summary,
    init_tracer_provider,
    inject_trace_context,
    run_id_to_trace_id,
    trace_case,
    trace_guardrail_event,
)


def _load_sample_case() -> LabelledCase:
    cases_dir = Path(__file__).resolve().parents[1] / "data" / "cases"
    case_path = cases_dir / "case_001.json"
    with open(case_path, encoding="utf-8") as f:
        return LabelledCase.model_validate(json.load(f))


def test_deterministic_trace_id_generation():
    """Verify that a given run_id generates a deterministic 128-bit integer trace ID."""
    run_id = "run_case_001_exp42"
    tid_1 = run_id_to_trace_id(run_id)
    tid_2 = run_id_to_trace_id(run_id)
    assert tid_1 == tid_2
    assert 1 <= tid_1 < (1 << 128)

    # Different run IDs yield different trace IDs
    tid_3 = run_id_to_trace_id("run_case_002_exp42")
    assert tid_1 != tid_3


def test_single_case_one_trace_hierarchy():
    """Verify one case execution produces exactly one trace containing root and child agent spans."""
    clear_spans()
    case = _load_sample_case()
    board_client = BlackboardClient(base_url="http://127.0.0.1:8001")
    orchestrator = Orchestrator()

    run_id = "test_otel_case_run_01"
    config = RunConfig(
        mode=Mode.BLACKBOARD,
        pattern=Pattern.SEQUENTIAL,
        reasoning=Reasoning.PLAIN,
        persona=Persona.COOPERATIVE,
        case_id=case.case_id,
        guardrails_enabled=True,
    )

    report = orchestrator.run_case(case, board_client, run_id, config)
    assert report.decision.value == "approve"

    # Inspect captured OpenTelemetry spans
    spans = get_finished_spans()
    assert len(spans) >= 4, f"Expected multiple spans for workflow, got {len(spans)}"

    expected_trace_id_int = run_id_to_trace_id(run_id)
    case_spans = [s for s in spans if s.context.trace_id == expected_trace_id_int]
    assert len(case_spans) >= 4, f"All case child spans must share trace_id {expected_trace_id_int}"

    span_names = [s.name for s in case_spans]
    assert f"case_onboarding:{case.case_id}" in span_names
    assert any("adk.gateway" in name for name in span_names)
    assert any("adk.extractor" in name for name in span_names)
    assert any("screening_crew" in name for name in span_names)
    assert any("adk.risk_scorer" in name for name in span_names)


def test_guardrail_event_tracing():
    """Verify GuardrailEvents create dedicated OpenTelemetry telemetry spans."""
    clear_spans()
    event = GuardrailEvent(
        event_id="evt_test_otel_123",
        stage="input",
        category="prompt_injection",
        action="blocked",
        agent_id="adk.gateway",
        score=1.0,
        detail="Blocked jailbreak instruction",
    )
    trace_guardrail_event(event)

    spans = get_finished_spans()
    assert len(spans) == 1
    g_span = spans[0]
    assert g_span.name == "guardrail:input:prompt_injection"
    assert g_span.attributes.get("guardrail.action") == "blocked"
    assert g_span.attributes.get("guardrail.score") == 1.0


def test_a2a_trace_context_propagation():
    """Verify W3C TraceContext headers are injected and extracted for A2A distributed calls."""
    run_id = "test_a2a_prop_run"
    with trace_case(run_id, "case_001"):
        headers: dict[str, str] = {}
        inject_trace_context(headers)
        assert "traceparent" in headers, "W3C traceparent header must be injected"

        # Verify extraction
        ctx = extract_trace_context(headers)
        assert ctx is not None


def test_provenance_audit_summary():
    """Verify get_provenance_summary produces audit verification evidence without PII."""
    clear_spans()
    case = _load_sample_case()
    board_client = BlackboardClient(base_url="http://127.0.0.1:8001")
    orchestrator = Orchestrator()

    run_id = "test_audit_provenance_01"
    config = RunConfig(
        mode=Mode.BLACKBOARD,
        pattern=Pattern.SEQUENTIAL,
        reasoning=Reasoning.PLAIN,
        persona=Persona.COOPERATIVE,
        case_id=case.case_id,
        guardrails_enabled=True,
    )
    _ = orchestrator.run_case(case, board_client, run_id, config)

    summary = get_provenance_summary(run_id)
    assert summary["run_id"] == run_id
    assert summary["provenance_verified"] is True
    assert summary["total_spans"] >= 4
    assert len(summary["trace_id_hex"]) == 32
    assert "adk.gateway" in summary["agents_traced"]
    assert "adk.risk_scorer" in summary["agents_traced"]


def test_init_tracer_provider_idempotency():
    """Verify tracer provider initialization is safe and idempotent."""
    provider1 = init_tracer_provider()
    provider2 = init_tracer_provider()
    assert provider1 is provider2

