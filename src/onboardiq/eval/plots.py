"""Evaluation Plot Generator.

Per docs/05_EVALUATION.md Section 4 and docs/06_IMPLEMENTATION_PLAN.md T16:
- Runtime by pattern boxplot (Sequential vs Parallel).
- Agent x Phase latency heatmap.
Saves PNG plots to results/plots/.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import matplotlib

# Headless backend for server/CLI environments
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def generate_plots(
    results_dir: str | Path = "results",
    metrics_csv: str | Path = "results/metrics.csv",
    plots_dir: str | Path = "results/plots",
) -> list[Path]:
    """Generate benchmark evaluation plots from metrics and traces."""
    res_path = Path(results_dir)
    csv_file = Path(metrics_csv)
    plot_path = Path(plots_dir)
    plot_path.mkdir(parents=True, exist_ok=True)
    generated_plots: list[Path] = []

    if not csv_file.exists():
        print(f"Metrics CSV not found at {csv_file}. Run metrics.py first.")
        return []

    # Read metrics CSV
    with open(csv_file, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    if not rows:
        print("No metrics rows found to plot.")
        return []

    # ---------------------------------------------------------
    # Plot 1: Runtime Distribution by Pattern (Boxplot)
    # ---------------------------------------------------------
    seq_runtimes = [float(r["runtime_s"]) for r in rows if r["pattern"] == "sequential"]
    par_runtimes = [float(r["runtime_s"]) for r in rows if r["pattern"] == "parallel"]

    fig, ax = plt.subplots(figsize=(7, 5))
    plot_data = []
    labels = []

    if seq_runtimes:
        plot_data.append(seq_runtimes)
        labels.append(f"Sequential\n(n={len(seq_runtimes)})")
    if par_runtimes:
        plot_data.append(par_runtimes)
        labels.append(f"Parallel\n(n={len(par_runtimes)})")

    box = ax.boxplot(plot_data, tick_labels=labels, patch_artist=True)
    colors = ["#4C72B0", "#55A868"]
    for patch, color in zip(box["boxes"], colors):
        patch.set_facecolor(color)
        patch.set_alpha(0.7)

    ax.set_title("Onboarding Runtime Distribution by Pattern", fontsize=13, fontweight="bold")
    ax.set_ylabel("Total Runtime (seconds)", fontsize=11)
    ax.grid(axis="y", linestyle="--", alpha=0.6)

    boxplot_path = plot_path / "runtime_by_pattern.png"
    plt.tight_layout()
    plt.savefig(boxplot_path, dpi=200)
    plt.close()
    generated_plots.append(boxplot_path)
    print(f"Generated: {boxplot_path}")

    # ---------------------------------------------------------
    # Plot 2: Agent x Phase Latency Heatmap
    # ---------------------------------------------------------
    # Aggregate latencies from all traces.json in results/
    agent_list = [
        "adk.gateway",
        "adk.extractor",
        "crewai.identity_verifier",
        "crewai.sanctions_screener",
        "crewai.ubo_analyst",
        "adk.risk_scorer",
    ]
    phase_list = ["intake", "extraction", "screening", "risk"]

    matrix = {agent: {phase: 0.0 for phase in phase_list} for agent in agent_list}
    counts = {agent: {phase: 0 for phase in phase_list} for agent in agent_list}

    for run_dir in res_path.iterdir():
        tr_file = run_dir / "traces.json"
        if tr_file.exists():
            try:
                with open(tr_file, encoding="utf-8") as f_tr:
                    traces = json.load(f_tr)
                for tr in traces:
                    ag = tr.get("agent_id")
                    ph = tr.get("phase")
                    lat = float(tr.get("latency_ms", 0.0))
                    if ag in matrix and ph in matrix[ag]:
                        matrix[ag][ph] += lat
                        counts[ag][ph] += 1
            except (json.JSONDecodeError, OSError):
                continue

    # Compute mean latency
    grid_data = []
    for ag in agent_list:
        row_vals = []
        for ph in phase_list:
            cnt = counts[ag][ph]
            val = (matrix[ag][ph] / cnt) if cnt > 0 else 0.0
            row_vals.append(val)
        grid_data.append(row_vals)

    fig, ax = plt.subplots(figsize=(8, 6))
    cax = ax.imshow(grid_data, cmap="YlGnBu", aspect="auto")

    ax.set_xticks(range(len(phase_list)))
    ax.set_xticklabels([p.title() for p in phase_list], fontsize=10, fontweight="bold")
    ax.set_yticks(range(len(agent_list)))
    agent_display = [a.replace("crewai.", "CrewAI: ").replace("adk.", "ADK: ") for a in agent_list]
    ax.set_yticklabels(agent_display, fontsize=10)

    # Annotate numeric values inside cells
    for i in range(len(agent_list)):
        for j in range(len(phase_list)):
            val = grid_data[i][j]
            color = "white" if val > 40.0 else "black"
            text = f"{val:.1f}ms" if val > 0 else "-"
            ax.text(j, i, text, ha="center", va="center", color=color, fontsize=9)

    ax.set_title("Agent x Phase Latency Heatmap (Mean ms)", fontsize=13, fontweight="bold")
    cbar = fig.colorbar(cax)
    cbar.set_label("Latency (ms)", rotation=270, labelpad=15)

    heatmap_path = plot_path / "agent_phase_heatmap.png"
    plt.tight_layout()
    plt.savefig(heatmap_path, dpi=200)
    plt.close()
    generated_plots.append(heatmap_path)
    print(f"Generated: {heatmap_path}")

    return generated_plots


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate evaluation plots from benchmark results")
    parser.add_argument("--results", default="results", help="Directory containing run results")
    parser.add_argument("--metrics", default="results/metrics.csv", help="Path to metrics.csv")
    parser.add_argument("--plots", default="results/plots", help="Directory to save plot images")
    args = parser.parse_args()

    generate_plots(results_dir=args.results, metrics_csv=args.metrics, plots_dir=args.plots)


if __name__ == "__main__":
    main()
