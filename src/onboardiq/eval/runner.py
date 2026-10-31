"""Evaluation Runner for OnboardIQ.

Per docs/05_EVALUATION.md Section 5 and docs/06_IMPLEMENTATION_PLAN.md T30:
- Reads a YAML grid of configurations (configs/grid.yaml).
- Provides pre-run cost and time estimation.
- Supports resuming from previous runs (--resume).
- Injects persona variants dynamically.
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
from onboardiq.guardrails.persona_injector import inject_persona
from onboardiq.schema import LabelledCase, Mode, Pattern, Persona, Reasoning, RunConfig


def estimate_grid_cost_and_time(
    grid_path: str | Path,
    avg_latency_per_run_s: float = 0.95,
    avg_cost_per_run_usd: float = 0.00025,
) -> dict[str, Any]:
    """Estimate total runtime and token cost prior to executing the evaluation sweep."""
    grid_file = Path(grid_path)
    with open(grid_file, encoding="utf-8") as f:
        config_data = yaml.safe_load(f)

    runs = config_data.get("runs", [])
    total_runs = len(runs)

    projected_seconds = total_runs * avg_latency_per_run_s
    projected_minutes = projected_seconds / 60.0
    projected_cost = total_runs * avg_cost_per_run_usd

    summary = {
        "grid_file": str(grid_file),
        "total_runs": total_runs,
        "avg_latency_per_run_s": avg_latency_per_run_s,
        "projected_runtime_s": round(projected_seconds, 2),
        "projected_runtime_min": round(projected_minutes, 2),
        "projected_cost_usd": round(projected_cost, 6),
    }

    print("\n" + "=" * 70)
    print("EVALUATION SWEEP PRE-RUN ESTIMATION")
    print("=" * 70)
    print(f"Grid Configuration:  {grid_file}")
    print(f"Total Runs:          {total_runs}")
    print(f"Projected Runtime:   {projected_seconds:.1f}s ({projected_minutes:.2f} minutes)")
    print(f"Projected Cost:      ${projected_cost:.5f} USD")
    print("=" * 70 + "\n")

    return summary


def run_grid(
    grid_path: str | Path,
    out_dir: str | Path = "results",
    cases_dir: str | Path = "data/cases",
    resume: bool = True,
    estimate_only: bool = False,
) -> dict[str, Any]:
    """Execute evaluation sweep across configurations defined in a YAML grid."""
    grid_file = Path(grid_path)
    out_path = Path(out_dir)
    cases_path = Path(cases_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    # Pre-run estimation check
    estimates = estimate_grid_cost_and_time(grid_file)
    if estimate_only:
        return estimates

    with open(grid_file, encoding="utf-8") as f:
        config_data = yaml.safe_load(f)

    runs = config_data.get("runs", [])
    total_runs = len(runs)
    succeeded = 0
    failed = 0
    skipped = 0
    results_summary: list[dict[str, Any]] = []

    print(f"\nStarting Evaluation Sweep: {total_runs} configurations from {grid_file}")
    print("=" * 80)

    for i, item in enumerate(runs, 1):
        case_id = item["case_id"]
        mode_val = Mode(item.get("mode", "blackboard"))
        pattern_val = Pattern(item.get("pattern", "sequential"))
        persona_val = Persona(item.get("persona", "cooperative"))
        reasoning_val = Reasoning(item.get("reasoning", "plain"))
        guardrails_enabled = item.get("guardrails_enabled", True)

        run_id = f"eval_{case_id}_{mode_val.value[:2]}_{pattern_val.value[:3]}_{persona_val.value[:3]}_{i:02d}"
        run_out_dir = out_path / run_id
        run_out_dir.mkdir(parents=True, exist_ok=True)

        # Check for resume support
        rep_file = run_out_dir / "report.json"
        if resume and rep_file.exists():
            try:
                with open(rep_file, encoding="utf-8") as f_cached:
                    cached_report = json.load(f_cached)
                print(
                    f"[{i}/{total_runs}] RESUME: {run_id:<32} | "
                    f"Cached Decision: {cached_report.get('decision', 'unknown'):<12} | "
                    f"Tier: {cached_report.get('risk_tier', 'unknown'):<6}"
                )
                succeeded += 1
                skipped += 1
                results_summary.append({
                    "run_id": run_id,
                    "case_id": case_id,
                    "status": "cached",
                    "decision": cached_report.get("decision"),
                    "tier": cached_report.get("risk_tier"),
                    "runtime_s": cached_report.get("total_runtime_s", 0.0),
                })
                continue
            except (OSError, json.JSONDecodeError, KeyError):
                pass

        case_file = cases_path / f"{case_id}.json"
        if not case_file.exists():
            print(f"[{i}/{total_runs}] SKIP: Case file not found: {case_file}")
            failed += 1
            continue

        with open(case_file, encoding="utf-8") as f:
            case = LabelledCase.model_validate_json(f.read())

        # Inject persona if non-cooperative
        if persona_val != Persona.COOPERATIVE:
            case, _ = inject_persona(case, persona_val)

        config = RunConfig(
            case_id=case.case_id,
            mode=mode_val,
            pattern=pattern_val,
            persona=persona_val,
            reasoning=reasoning_val,
            seed=item.get("seed", 42),
            guardrails_enabled=guardrails_enabled,
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
                f"[{i}/{total_runs}] SUCCESS: {run_id:<32} | "
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
            print(f"[{i}/{total_runs}] ERROR: {run_id:<32} | Exception: {exc}")
            results_summary.append({
                "run_id": run_id,
                "case_id": case_id,
                "status": "error",
                "error": str(exc),
            })

    print("=" * 80)
    print(f"Sweep Completed: {succeeded}/{total_runs} completed ({skipped} cached, {failed} failed)\n")

    return {
        "total": total_runs,
        "succeeded": succeeded,
        "skipped": skipped,
        "failed": failed,
        "runs": results_summary,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="OnboardIQ Full Evaluation Runner")
    parser.add_argument("--grid", default="configs/grid.yaml", help="Path to evaluation YAML grid")
    parser.add_argument("--out", default="results", help="Directory to save run results")
    parser.add_argument("--no-resume", action="store_true", help="Do not resume cached runs; force re-execution")
    parser.add_argument("--estimate-only", action="store_true", help="Print time and cost estimates without executing")
    args = parser.parse_args()

    run_grid(
        grid_path=args.grid,
        out_dir=args.out,
        resume=not args.no_resume,
        estimate_only=args.estimate_only,
    )


if __name__ == "__main__":
    main()
