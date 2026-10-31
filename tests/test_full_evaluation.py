"""Tests for Task T30: Full evaluation grid sweep, metrics calculation, and plot generation."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import yaml

from onboardiq.eval.runner import estimate_grid_cost_and_time


def test_grid_yaml_definition():
    """Verify configs/grid.yaml contains >= 40 runs and covers required evaluation factors."""
    grid_path = Path("configs/grid.yaml")
    assert grid_path.exists(), "configs/grid.yaml must exist"

    with open(grid_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    runs = data.get("runs", [])
    assert len(runs) >= 40, f"Grid must define >= 40 runs, found {len(runs)}"

    modes = {r.get("mode") for r in runs}
    patterns = {r.get("pattern") for r in runs}
    personas = {r.get("persona") for r in runs}

    assert {"blackboard", "hybrid_p2p"}.issubset(modes)
    assert {"sequential", "parallel"}.issubset(patterns)
    assert {"cooperative", "impatient", "abusive", "forger", "injecting"}.issubset(personas)


def test_runner_estimation():
    """Verify estimate_grid_cost_and_time computes runtime and cost projections."""
    estimates = estimate_grid_cost_and_time("configs/grid.yaml")
    assert estimates["total_runs"] >= 40
    assert estimates["projected_runtime_s"] > 0
    assert estimates["projected_cost_usd"] > 0


def test_metrics_csv_outputs():
    """Verify results/metrics.csv exists and contains all required evaluation columns."""
    metrics_path = Path("results/metrics.csv")
    assert metrics_path.exists(), "results/metrics.csv must exist"

    with open(metrics_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    assert len(rows) >= 40, f"Expected >= 40 metric rows, found {len(rows)}"

    required_cols = [
        "run_id", "case_id", "mode", "pattern", "persona", "decision",
        "expected_decision", "decision_correct", "risk_tier", "expected_tier",
        "tier_correct", "runtime_s", "tokens", "cost_usd", "red_flag_recall",
        "false_positive", "guardrail_events", "injection_succeeded"
    ]
    for col in required_cols:
        assert col in rows[0], f"Column '{col}' missing from results/metrics.csv"


def test_plots_and_statistical_tests_generated():
    """Verify all benchmark plots and statistical test outputs exist in results/plots/."""
    plots_dir = Path("results/plots")
    assert plots_dir.exists()

    expected_plots = [
        "runtime_and_cost_boxplots.png",
        "red_flag_recall_by_persona.png",
        "tokens_per_run_by_mode.png",
        "injection_ablation_bar_chart.png",
        "heatmap_agent_phase_latency.png",
        "heatmap_agent_step_type.png",
        "heatmap_agent_errors_guardrails.png",
    ]
    for plot_name in expected_plots:
        p = plots_dir / plot_name
        assert p.exists(), f"Plot '{plot_name}' not found in {plots_dir}"
        assert p.stat().st_size > 1000, f"Plot '{plot_name}' file size too small"

    stat_file = plots_dir / "statistical_tests.json"
    assert stat_file.exists()
    with open(stat_file, encoding="utf-8") as f:
        stat_data = json.load(f)
    assert len(stat_data) >= 2


def test_summary_markdown_file():
    """Verify results/SUMMARY.md exists and contains real evaluation statistics."""
    summary_path = Path("results/SUMMARY.md")
    assert summary_path.exists()
    content = summary_path.read_text(encoding="utf-8")
    assert "OnboardIQ Full Benchmark Evaluation Summary" in content
    assert "Dataset Description and Composition" in content
    assert "Evaluation Grid Sweep Definition" in content
    assert "Mann-Whitney U Test" in content

