"""Tests for Evaluation Runner v0, metrics calculation, and plot generation.

Per docs/06_IMPLEMENTATION_PLAN.md T16.
"""

from pathlib import Path

from onboardiq.eval.metrics import compute_metrics
from onboardiq.eval.plots import generate_plots
from onboardiq.eval.runner import run_grid


def test_eval_grid_runner_and_metrics(tmp_path: Path):
    # Create minimal grid
    grid_yaml = tmp_path / "test_grid.yaml"
    grid_yaml.write_text(
        """
runs:
  - case_id: "case_001"
    mode: "blackboard"
    pattern: "sequential"
  - case_id: "case_001"
    mode: "hybrid_p2p"
    pattern: "parallel"
"""
    )

    out_dir = tmp_path / "results"
    summary = run_grid(grid_path=grid_yaml, out_dir=out_dir, cases_dir="data/cases")

    assert summary["total"] == 2
    assert summary["succeeded"] == 2
    assert summary["failed"] == 0

    # Verify metrics computation
    metrics_csv = out_dir / "metrics.csv"
    rows = compute_metrics(results_dir=out_dir, cases_dir="data/cases", out_csv=metrics_csv)
    assert len(rows) == 2
    assert metrics_csv.exists()

    # Verify plots generation
    plots_dir = out_dir / "plots"
    plots = generate_plots(results_dir=out_dir, metrics_csv=metrics_csv, plots_dir=plots_dir)
    assert len(plots) >= 2
    assert (plots_dir / "runtime_and_cost_boxplots.png").exists()

