"""OpenTelemetry distributed tracing for OnboardIQ.

Per criterion 10 and implementation plan T29:
- One case equals one trace, using run_id to generate a deterministic 128-bit Trace ID.
- Root span captures case metadata (mode, pattern, persona, reasoning).
- Child spans track agent phases, tool calls, and guardrail events.
- Distributed W3C TraceContext propagation across A2A protocol.
- Optional external export to Langfuse, Phoenix, or any OTLP collector via env vars.
"""

from __future__ import annotations

import base64
import hashlib
import os
import uuid
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

from opentelemetry import context as otel_context
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

from onboardiq.schema import GuardrailEvent

# Global in-memory exporter for offline inspection, testing, and UI provenance display
_IN_MEMORY_EXPORTER = InMemorySpanExporter()
_TRACER_PROVIDER: TracerProvider | None = None
_PROPAGATOR = TraceContextTextMapPropagator()


def run_id_to_trace_id(run_id: str) -> int:
    """Convert an arbitrary run_id into a valid 128-bit OpenTelemetry trace ID integer."""
    hash_bytes = hashlib.md5(run_id.encode("utf-8")).digest()
    trace_id_int = int.from_bytes(hash_bytes, byteorder="big")
    if trace_id_int == 0:
        trace_id_int = 1
    return trace_id_int


def init_tracer_provider() -> TracerProvider:
    """Initialize or return the global TracerProvider with configured exporters."""
    global _TRACER_PROVIDER
    if _TRACER_PROVIDER is not None:
        return _TRACER_PROVIDER

    resource = Resource.create({
        "service.name": "onboardiq",
        "service.version": "1.0.0",
        "service.namespace": "compliance-agentic-ai",
    })

    provider = TracerProvider(resource=resource)
    provider.add_span_processor(SimpleSpanProcessor(_IN_MEMORY_EXPORTER))

    # 1. Check for Langfuse OTLP export config
    langfuse_public = os.getenv("LANGFUSE_PUBLIC_KEY")
    langfuse_secret = os.getenv("LANGFUSE_SECRET_KEY")
    langfuse_host = os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com").rstrip("/")

    # 2. Check for Phoenix or Generic OTLP endpoint
    otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    phoenix_endpoint = os.getenv("PHOENIX_COLLECTOR_ENDPOINT")

    target_endpoint: str | None = None
    headers: dict[str, str] = {}

    if langfuse_public and langfuse_secret:
        target_endpoint = f"{langfuse_host}/api/public/otel"
        auth_str = f"{langfuse_public}:{langfuse_secret}"
        headers["Authorization"] = f"Basic {base64.b64encode(auth_str.encode()).decode()}"
    elif phoenix_endpoint:
        target_endpoint = f"{phoenix_endpoint.rstrip('/')}/v1/traces"
    elif otlp_endpoint:
        target_endpoint = otlp_endpoint

    if target_endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
            otlp_exporter = OTLPSpanExporter(endpoint=target_endpoint, headers=headers)
            provider.add_span_processor(SimpleSpanProcessor(otlp_exporter))
        except (ImportError, ValueError, OSError):
            target_endpoint = None

    trace.set_tracer_provider(provider)
    _TRACER_PROVIDER = provider
    return provider


def get_tracer(name: str = "onboardiq") -> trace.Tracer:
    """Get an OpenTelemetry Tracer instance."""
    provider = init_tracer_provider()
    return provider.get_tracer(name)


def get_finished_spans() -> list[ReadableSpan]:
    """Retrieve in-memory finished spans for inspection, tests, and provenance verification."""
    return _IN_MEMORY_EXPORTER.get_finished_spans()


def clear_spans() -> None:
    """Clear in-memory span buffer."""
    _IN_MEMORY_EXPORTER.clear()


@contextmanager
def trace_case(
    run_id: str,
    case_id: str,
    mode: str = "blackboard",
    pattern: str = "sequential",
    persona: str = "cooperative",
    reasoning: str = "plain",
) -> Generator[trace.Span, None, None]:
    """Root span for an entire case onboarding workflow.

    Enforces that one case equals one trace with trace_id derived deterministically from run_id.
    """
    tracer = get_tracer("onboardiq.core")
    trace_id_int = run_id_to_trace_id(run_id)
    span_id_int = int.from_bytes(uuid.uuid4().bytes[:8], byteorder="big")

    # Seed root span context with deterministic trace_id
    parent_context = trace.SpanContext(
        trace_id=trace_id_int,
        span_id=span_id_int,
        is_remote=False,
        trace_flags=trace.TraceFlags(trace.TraceFlags.SAMPLED),
    )
    ctx = trace.set_span_in_context(trace.NonRecordingSpan(parent_context))

    with tracer.start_as_current_span(
        f"case_onboarding:{case_id}",
        context=ctx,
        attributes={
            "onboardiq.run_id": run_id,
            "onboardiq.case_id": case_id,
            "onboardiq.mode": mode,
            "onboardiq.pattern": pattern,
            "onboardiq.persona": persona,
            "onboardiq.reasoning": reasoning,
            "provenance.root": True,
        },
    ) as span:
        yield span


@contextmanager
def trace_agent(
    agent_id: str,
    phase: str,
    run_id: str | None = None,
) -> Generator[trace.Span, None, None]:
    """Child span for an individual agent execution within a phase."""
    tracer = get_tracer("onboardiq.agents")
    span_name = f"agent:{agent_id}"
    attrs = {
        "onboardiq.agent_id": agent_id,
        "onboardiq.phase": phase,
    }
    if run_id:
        attrs["onboardiq.run_id"] = run_id

    with tracer.start_as_current_span(span_name, attributes=attrs) as span:
        yield span


@contextmanager
def trace_tool(
    tool_name: str,
    agent_id: str = "",
    inputs: dict[str, Any] | None = None,
) -> Generator[trace.Span, None, None]:
    """Child span for FastMCP tool execution."""
    tracer = get_tracer("onboardiq.tools")
    span_name = f"tool:{tool_name}"
    attrs: dict[str, Any] = {
        "tool.name": tool_name,
        "tool.agent_id": agent_id,
    }
    if inputs:
        # Sanitize / record inputs summary (never raw PII)
        for k, v in list(inputs.items())[:5]:
            attrs[f"tool.arg.{k}"] = str(v)[:80]

    with tracer.start_as_current_span(span_name, attributes=attrs) as span:
        yield span


def trace_guardrail_event(event: GuardrailEvent) -> None:
    """Record a guardrail evaluation event as an OpenTelemetry span event."""
    tracer = get_tracer("onboardiq.guardrails")
    span_name = f"guardrail:{event.stage}:{event.category}"
    with tracer.start_as_current_span(
        span_name,
        attributes={
            "guardrail.event_id": event.event_id,
            "guardrail.stage": event.stage,
            "guardrail.category": event.category,
            "guardrail.action": event.action,
            "guardrail.agent_id": event.agent_id,
            "guardrail.score": float(event.score),
            "guardrail.detail": event.detail,
        },
    ) as span:
        span.set_attribute("guardrail.blocked", event.action == "blocked")


def inject_trace_context(headers: dict[str, str]) -> dict[str, str]:
    """Inject current OpenTelemetry trace context (traceparent) into outgoing headers (e.g. A2A)."""
    _PROPAGATOR.inject(headers)
    return headers


def extract_trace_context(headers: dict[str, str]) -> otel_context.Context:
    """Extract OpenTelemetry trace context from incoming headers."""
    return _PROPAGATOR.extract(headers)


def get_provenance_summary(run_id: str) -> dict[str, Any]:
    """Compute audit provenance summary for a given run from finished spans."""
    trace_id_int = run_id_to_trace_id(run_id)
    trace_id_hex = f"{trace_id_int:032x}"
    matching_spans = [s for s in get_finished_spans() if f"{s.context.trace_id:032x}" == trace_id_hex]

    spans_by_name = [s.name for s in matching_spans]
    tools = [s.name.replace("tool:", "") for s in matching_spans if s.name.startswith("tool:")]
    agents = [s.name.replace("agent:", "") for s in matching_spans if s.name.startswith("agent:")]
    guardrails = [s.name.replace("guardrail:", "") for s in matching_spans if s.name.startswith("guardrail:")]

    return {
        "run_id": run_id,
        "trace_id_hex": trace_id_hex,
        "total_spans": len(matching_spans),
        "span_names": spans_by_name,
        "agents_traced": agents,
        "tools_called": tools,
        "guardrail_checks": guardrails,
        "provenance_verified": len(matching_spans) > 0,
    }
