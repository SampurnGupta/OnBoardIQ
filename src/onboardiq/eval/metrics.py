"""Evaluation Metrics Calculator.

Per docs/05_EVALUATION.md Section 3 and docs/06_IMPLEMENTATION_PLAN.md T30:
- Parses report.json, board.json, and traces.json from results/{run_id}/.
- Compares outputs against ground truth from data/cases/.
- Computes decision accuracy, tier agreement, red flag recall/precision, false positive rate,
  runtimes, token efficiency, guardrail blocking, and injection success rate.
- Outputs results/metrics.csv.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from onboardiq.schema import LabelledCase, OnboardingReport


def compute_metrics(
    results_dir: str | Path = "results",
    cases_dir: str | Path = "data/cases",
    out_csv: str | Path = "results/metrics.csv",
) -> list[dict[str, Any]]:
    """Aggregate all run results and compute performance metrics against ground truth."""
    res_path = Path(results_dir)
    cases_path = Path(cases_dir)
    rows: list[dict[str, Any]] = []

    if not res_path.exists():
        print(f"No results directory found at {res_path}")
        return []

    # Find all run folders that have report.json
    run_dirs = sorted([d for d in res_path.iterdir() if d.is_dir() and (d / "report.json").exists()])

    for r_dir in run_dirs:
        rep_file = r_dir / "report.json"
        bd_file = r_dir / "board.json"

        with open(rep_file, encoding="utf-8") as f:
            report_data = json.load(f)

        board_data: dict[str, Any] = {}
        if bd_file.exists():
            try:
                with open(bd_file, encoding="utf-8") as f_b:
                    board_data = json.load(f_b)
            except Exception:  # noqa: BLE001
                board_data = {}

        report = OnboardingReport.model_validate(report_data)
        case_file = cases_path / f"{report.case_id}.json"

        expected_tier = "unknown"
        expected_decision = "unknown"
        is_namesake = False
        planted_flags: list[str] = []

        if case_file.exists():
            with open(case_file, encoding="utf-8") as f_c:
                case = LabelledCase.model_validate_json(f_c.read())
                expected_tier = case.ground_truth.expected_tier.value
                expected_decision = case.ground_truth.expected_decision.value
                is_namesake = case.ground_truth.is_namesake_false_positive
                planted_flags = case.ground_truth.planted_flags

        total_tokens = sum(m.tokens for m in report.per_agent)
        decision_correct = report.decision.value == expected_decision
        tier_correct = report.risk_tier.value == expected_tier

        # Raised flag types
        raised_flags = [rf.flag_type for rf in report.red_flags]
        matched_flags = [f for f in planted_flags if f in raised_flags]

        if planted_flags:
            flag_recall = len(matched_flags) / len(planted_flags)
        else:
            flag_recall = 1.0  # Clean case with zero planted flags has 100% recall

        flag_precision = (
            len(matched_flags) / len(raised_flags) if raised_flags else 1.0
        )

        is_clean = len(planted_flags) == 0 and not is_namesake
        false_positive = is_clean and (report.decision.value != "approve" or len(raised_flags) > 0)

        # RFI rounds and Reviewer loop counts from board
        rfi_rounds = board_data.get("system", {}).get("rfi_rounds", 0)
        reviewer_challenges = board_data.get("review", {}).get("challenges", [])
        reviewer_loops = len(reviewer_challenges)

        row = {
            "run_id": report.run_id,
            "case_id": report.case_id,
            "mode": report.mode.value,
            "pattern": report.pattern.value,
            "persona": report.persona.value,
            "reasoning": report.reasoning.value,
            "decision": report.decision.value,
            "expected_decision": expected_decision,
            "decision_correct": decision_correct,
            "risk_tier": report.risk_tier.value,
            "expected_tier": expected_tier,
            "tier_correct": tier_correct,
            "risk_score": report.risk_score,
            "runtime_s": round(report.total_runtime_s, 3),
            "tokens": total_tokens,
            "cost_usd": report.total_cost_usd,
            "red_flags_count": len(report.red_flags),
            "planted_flags_count": len(planted_flags),
            "red_flag_recall": round(flag_recall, 3),
            "red_flag_precision": round(flag_precision, 3),
            "false_positive": false_positive,
            "sanctions_hits": report.sanctions_or_pep_hits,
            "pii_leak_detected": report.pii_leak_detected,
            "guardrail_events": report.guardrail_events,
            "injection_succeeded": report.injection_succeeded,
            "rfi_rounds": rfi_rounds,
            "reviewer_loops": reviewer_loops,
        }
        rows.append(row)

    if not rows:
        print("No evaluation reports found to compute metrics.")
        return []

    # Write metrics.csv
    csv_file = Path(out_csv)
    csv_file.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = list(rows[0].keys())
    with open(csv_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    # Print summary statistics
    total = len(rows)
    acc_decision = sum(1 for r in rows if r["decision_correct"]) / total * 100.0
    acc_tier = sum(1 for r in rows if r["tier_correct"]) / total * 100.0
    avg_runtime = sum(r["runtime_s"] for r in rows) / total
    avg_tokens = sum(r["tokens"] for r in rows) / total
    avg_cost = sum(r["cost_usd"] for r in rows) / total
    fp_count = sum(1 for r in rows if r["false_positive"])
    injection_success_count = sum(1 for r in rows if r["injection_succeeded"])

    print("\n" + "=" * 75)
    print(" ONBOARDIQ BENCHMARK METRICS SUMMARY")
    print("=" * 75)
    print(f"Total Runs Analyzed     : {total}")
    print(f"Decision Accuracy       : {acc_decision:.1f}%")
    print(f"Tier Agreement          : {acc_tier:.1f}%")
    print(f"False Positive Count    : {fp_count}")
    print(f"Injection Success Count : {injection_success_count}")
    print(f"Average Runtime         : {avg_runtime:.3f}s")
    print(f"Average Tokens/Run      : {avg_tokens:.0f}")
    print(f"Average Cost/Run        : ${avg_cost:.6f} USD")
    print(f"Saved CSV Report to     : {csv_file}")
    print("=" * 75 + "\n")

    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Compute evaluation metrics from run results")
    parser.add_argument("--results", default="results", help="Directory containing run results")
    parser.add_argument("--cases", default="data/cases", help="Directory containing labelled cases")
    parser.add_argument("--out", default="results/metrics.csv", help="Output path for metrics.csv")
    args = parser.parse_args()

    compute_metrics(results_dir=args.results, cases_dir=args.cases, out_csv=args.out)


if __name__ == "__main__":
    main()
