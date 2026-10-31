#!/usr/bin/env python3
"""Run one case across all four mode/pattern combinations and display a comparison table.

Per docs/06_IMPLEMENTATION_PLAN.md T14:
Modes: blackboard, hybrid_p2p
Patterns: sequential, parallel
"""

from __future__ import annotations

import argparse
from pathlib import Path

from onboardiq.agents.adk.orchestrator import Orchestrator
from onboardiq.blackboard.client import BlackboardClient
from onboardiq.blackboard.service import app
from onboardiq.blackboard.store import SQLiteBlackboardStore
from onboardiq.schema import LabelledCase, Mode, Pattern, RunConfig


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare Modes and Patterns for OnboardIQ")
    parser.add_argument("--case", default="case_001", help="Case to evaluate (e.g. case_001)")
    args = parser.parse_args()

    case_path = Path("data/cases") / f"{args.case}.json"
    if not case_path.exists():
        print(f"Error: {case_path} not found")
        return

    with open(case_path, encoding="utf-8") as f:
        case = LabelledCase.model_validate_json(f.read())

    combos = [
        (Mode.BLACKBOARD, Pattern.SEQUENTIAL),
        (Mode.BLACKBOARD, Pattern.PARALLEL),
        (Mode.HYBRID_P2P, Pattern.SEQUENTIAL),
        (Mode.HYBRID_P2P, Pattern.PARALLEL),
    ]

    results = []

    print(f"\nEvaluating Case {case.case_id} across all 4 configurations...\n")
    for mode, pattern in combos:
        app.state.store = SQLiteBlackboardStore(db_path=":memory:")
        client = BlackboardClient(base_url="http://testserver", app=app)
        orch = Orchestrator()

        config = RunConfig(
            case_id=case.case_id,
            mode=mode,
            pattern=pattern,
        )

        report = orch.run_case(case=case, board_client=client, config=config)

        total_tokens = sum(m.tokens for m in report.per_agent)
        results.append({
            "mode": mode.value,
            "pattern": pattern.value,
            "decision": report.decision.value,
            "tier": report.risk_tier.value,
            "score": report.risk_score,
            "runtime_s": report.total_runtime_s,
            "tokens": total_tokens,
            "cost_usd": report.total_cost_usd,
        })

    print("=" * 95)
    print(f"{'Mode':<14} | {'Pattern':<12} | {'Decision':<10} | {'Tier':<8} | {'Score':<6} | {'Runtime (s)':<12} | {'Tokens':<8} | {'Cost ($)':<10}")
    print("-" * 95)
    for r in results:
        print(f"{r['mode']:<14} | {r['pattern']:<12} | {r['decision']:<10} | {r['tier']:<8} | {r['score']:<6.1f} | {r['runtime_s']:<12.3f} | {r['tokens']:<8} | ${r['cost_usd']:<9.6f}")
    print("=" * 95 + "\n")


if __name__ == "__main__":
    main()

