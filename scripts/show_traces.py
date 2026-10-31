#!/usr/bin/env python3
"""CLI utility to display telemetry traces for a run.

Per docs/06_IMPLEMENTATION_PLAN.md T12:
Prints a per-agent summary table with latency, tokens, cost, and errors.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from onboardiq.agents.adk.orchestrator import Orchestrator
from onboardiq.blackboard.client import BlackboardClient
from onboardiq.blackboard.service import app
from onboardiq.blackboard.store import SQLiteBlackboardStore
from onboardiq.schema import LabelledCase


def main() -> None:
    parser = argparse.ArgumentParser(description="Display per-agent telemetry traces for OnboardIQ run")
    parser.add_argument("--case", default="case_001", help="Case ID to run and display traces for (e.g. case_001)")
    parser.add_argument("--use-a2a", action="store_true", help="Invoke Screening Crew over A2A protocol")
    parser.add_argument("--pattern", default="sequential", choices=["sequential", "parallel"], help="Execution pattern")
    parser.add_argument("--mode", default="blackboard", choices=["blackboard", "hybrid_p2p"], help="Messaging mode")
    args = parser.parse_args()

    # Load case
    case_path = Path("data/cases") / f"{args.case}.json"
    if not case_path.exists():
        print(f"Error: Case file not found at {case_path}")
        return

    with open(case_path, encoding="utf-8") as f:
        case = LabelledCase.model_validate_json(f.read())

    # Set up in-memory blackboard
    app.state.store = SQLiteBlackboardStore(db_path=":memory:")
    board_client = BlackboardClient(base_url="http://testserver", app=app)

    orchestrator = Orchestrator()
    print(f"Executing {case.case_id} ({case.declared_name}) with telemetry logging...")
    report = orchestrator.run_case(
        case=case,
        board_client=board_client,
        use_a2a=args.use_a2a,
    )

    # Fetch traces from blackboard
    board = board_client.get_run(report.run_id, agent_id="adk.orchestrator")
    traces = board.system.traces

    print("\n" + "=" * 90)
    print(f" TELEMETRY TRACES FOR RUN: {report.run_id} | DECISION: {report.decision.value.upper()}")
    print("=" * 90)
    print(f"{'Agent ID':<26} | {'Phase':<12} | {'Step Type':<10} | {'Latency (ms)':<12} | {'Tokens':<8} | {'Cost ($)':<10}")
    print("-" * 90)

    total_latency = 0.0
    total_tokens = 0
    total_cost = 0.0
    adk_traces = 0
    crewai_traces = 0

    for t in traces:
        step_tokens = t.prompt_tokens + t.completion_tokens
        total_latency += t.latency_ms
        total_tokens += step_tokens
        total_cost += t.cost_usd
        if "crewai" in t.agent_id:
            crewai_traces += 1
        elif "adk" in t.agent_id:
            adk_traces += 1

        agent_short = t.agent_id[:25]
        print(f"{agent_short:<26} | {t.phase.value:<12} | {t.step_type:<10} | {t.latency_ms:<12.1f} | {step_tokens:<8} | ${t.cost_usd:<9.6f}")

    print("-" * 90)
    print(f"{'TOTALS':<26} | {'ALL':<12} | {'-':<10} | {total_latency:<12.1f} | {total_tokens:<8} | ${total_cost:<9.6f}")
    print("=" * 90)
    print(f"Framework Traces: ADK = {adk_traces}, CrewAI = {crewai_traces}")
    print(f"Total Execution Runtime: {report.total_runtime_s:.2f}s")
    print("=" * 90 + "\n")


if __name__ == "__main__":
    main()
