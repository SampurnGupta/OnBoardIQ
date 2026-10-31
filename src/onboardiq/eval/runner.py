"""Evaluation Runner v0.

Per docs/05_EVALUATION.md Section 5 and docs/06_IMPLEMENTATION_PLAN.md T16:
- Reads a YAML grid of configurations.
- Executes each configuration through the Orchestrator, catching exceptions.
- Saves report.json, traces.json, and board.json under results/{run_id}/.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml

from onboardiq.agents.adk.orchestrator import Orchestrator
from onboardiq.blackboard.client import BlackboardClient
from onboardiq.blackboard.service import app
from onboardiq.blackboard.store import SQLiteBlackboardStore
from onboardiq.schema import LabelledCase, Mode, Pattern, Persona, Reasoning, RunConfig


def run_grid(
    grid_path: str | Path,
    out_dir: str | Path = "results",
    cases_dir: str | Path = "data/cases",
) -> dict[str, Any]:
    """Execute evaluation sweep across configurations defined in a YAML grid."""
    grid_file = Path(grid_path)
    out_path = Path(out_dir)
    cases_path = Path(cases_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    with open(grid_file, encoding="utf-8") as f:
        config_data = yaml.safe_load(f)

    runs = config_data.get("runs", [])
    total_runs = len(runs)
    succeeded = 0
    failed = 0
    results_summary: list[dict[str, Any]] = []

    print(f"\nStarting Evaluation Sweep: {total_runs} configurations from {grid_file}")
    print("=" * 80)

    for i, item in enumerate(runs, 1):
        case_id = item["case_id"]
        mode_val = Mode(item.get("mode", "blackboard"))
        pattern_val = Pattern(item.get("pattern", "sequential"))
        persona_val = Persona(item.get("persona", "cooperative"))
        reasoning_val = Reasoning(item.get("reasoning", "plain"))

        case_file = cases_path / f"{case_id}.json"
        if not case_file.exists():
            print(f"[{i}/{total_runs}] SKIP: Case file not found: {case_file}")
            failed += 1
            continue

        with open(case_file, encoding="utf-8") as f:
            case = LabelledCase.model_validate_json(f.read())

        run_id = f"eval_{case_id}_{mode_val.value[:2]}_{pattern_val.value[:3]}_{i:02d}"
        run_out_dir = out_path / run_id
        run_out_dir.mkdir(parents=True, exist_ok=True)

        config = RunConfig(
            case_id=case.case_id,
            mode=mode_val,
            pattern=pattern_val,
            persona=persona_val,
            reasoning=reasoning_val,
            seed=item.get("seed", 42),
            guardrails_enabled=item.get("guardrails_enabled", True),
        )

        try:
            # Fresh in-memory blackboard for reproducible isolated runs
            app.state.store = SQLiteBlackboardStore(db_path=":memory:")
            client = BlackboardClient(base_url="http://testserver", app=app)
            orch = Orchestrator()

            report = orch.run_case(
                case=case,
                board_client=client,
                run_id=run_id,
                config=config,
            )

            board = client.get_run(run_id, agent_id="adk.orchestrator")
            traces = [t.model_dump(mode="json") for t in board.system.traces]

            # Save artifacts
            with open(run_out_dir / "report.json", "w", encoding="utf-8") as f_rep:
                f_rep.write(report.model_dump_json(indent=2))

            with open(run_out_dir / "traces.json", "w", encoding="utf-8") as f_tr:
                json.dump(traces, f_tr, indent=2)

            with open(run_out_dir / "board.json", "w", encoding="utf-8") as f_bd:
                f_bd.write(board.model_dump_json(indent=2))

            succeeded += 1
            print(
                f"[{i}/{total_runs}] SUCCESS: {run_id:<25} | "
                f"Decision: {report.decision.value:<12} | "
                f"Tier: {report.risk_tier.value:<6} | "
                f"Runtime: {report.total_runtime_s:.2f}s"
            )
            results_summary.append({
                "run_id": run_id,
                "case_id": case_id,
                "status": "success",
                "decision": report.decision.value,
                "tier": report.risk_tier.value,
                "runtime_s": report.total_runtime_s,
            })

        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"[{i}/{total_runs}] ERROR: {run_id:<25} | Exception: {exc}")
            results_summary.append({
                "run_id": run_id,
                "case_id": case_id,
                "status": "error",
                "error": str(exc),
            })

    print("=" * 80)
    print(f"Sweep Completed: {succeeded}/{total_runs} succeeded ({failed} failed)\n")

    return {
        "total": total_runs,
        "succeeded": succeeded,
        "failed": failed,
        "runs": results_summary,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="OnboardIQ Evaluation Runner v0")
    parser.add_argument("--grid", default="configs/eval_v0.yaml", help="Path to evaluation YAML grid")
    parser.add_argument("--out", default="results", help="Directory to save run results")
    args = parser.parse_args()

    run_grid(grid_path=args.grid, out_dir=args.out)


if __name__ == "__main__":
    main()
