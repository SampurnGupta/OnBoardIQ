"""Evaluation Plot Generator for OnboardIQ.

Per docs/05_EVALUATION.md Section 4 and docs/06_IMPLEMENTATION_PLAN.md T30:
1. Boxplots of runtime and cost: Sequential vs Parallel; Blackboard vs Hybrid P2P.
2. Boxplot of red-flag recall by persona.
3. Boxplot of tokens per run by mode.
4. Bar chart: injection success rate, guardrails off vs on.
5. Heatmap agent x phase (latency).
6. Heatmap agent x step type (count or tokens).
7. Heatmap agent x error and guardrail triggers.
8. Statistical tests: Mann-Whitney U tests for mode and pattern runtime/tokens.

Saves high-resolution PNG plots to results/plots/.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy import stats


def generate_plots(
    results_dir: str | Path = "results",
    metrics_csv: str | Path = "results/metrics.csv",
    plots_dir: str | Path = "results/plots",
) -> list[Path]:
    """Generate all benchmark evaluation plots and statistical tests from metrics and traces."""
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

    # -------------------------------------------------------------------------
    # Plot 1: Runtime and Cost Boxplots (Sequential vs Parallel; Blackboard vs Hybrid P2P)
    # -------------------------------------------------------------------------
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5))

    seq_runtimes = [float(r["runtime_s"]) for r in rows if r["pattern"] == "sequential"]
    par_runtimes = [float(r["runtime_s"]) for r in rows if r["pattern"] == "parallel"]
    bb_runtimes = [float(r["runtime_s"]) for r in rows if r["mode"] == "blackboard"]
    p2p_runtimes = [float(r["runtime_s"]) for r in rows if r["mode"] == "hybrid_p2p"]

    box1 = ax1.boxplot(
        [seq_runtimes, par_runtimes, bb_runtimes, p2p_runtimes],
        tick_labels=["Sequential", "Parallel", "Blackboard", "Hybrid P2P"],
        patch_artist=True,
    )
    palette = ["#4C72B0", "#55A868", "#C44E52", "#8172B3"]
    for patch, color in zip(box1["boxes"], palette):
        patch.set_facecolor(color)
        patch.set_alpha(0.7)

    ax1.set_title("Runtime Comparison (Pattern & Mode)", fontsize=12, fontweight="bold")
    ax1.set_ylabel("Runtime (seconds)", fontsize=10)
    ax1.grid(axis="y", linestyle="--", alpha=0.5)

    seq_costs = [float(r["cost_usd"]) * 1000 for r in rows if r["pattern"] == "sequential"]
    par_costs = [float(r["cost_usd"]) * 1000 for r in rows if r["pattern"] == "parallel"]
    box2 = ax2.boxplot(
        [seq_costs, par_costs],
        tick_labels=["Sequential", "Parallel"],
        patch_artist=True,
    )
    for patch, color in zip(box2["boxes"], ["#4C72B0", "#55A868"]):
        patch.set_facecolor(color)
        patch.set_alpha(0.7)

    ax2.set_title("Estimated Cost per Run", fontsize=12, fontweight="bold")
    ax2.set_ylabel("Cost (mUSD / $0.001)", fontsize=10)
    ax2.grid(axis="y", linestyle="--", alpha=0.5)

    p1_path = plot_path / "runtime_and_cost_boxplots.png"
    plt.tight_layout()
    plt.savefig(p1_path, dpi=200)
    plt.close()
    generated_plots.append(p1_path)

    # -------------------------------------------------------------------------
    # Plot 2: Red Flag Recall by Persona
    # -------------------------------------------------------------------------
    personas = sorted({r["persona"] for r in rows})
    recall_by_persona = []
    for p in personas:
        recalls = [float(r["red_flag_recall"]) for r in rows if r["persona"] == p]
        recall_by_persona.append(recalls if recalls else [1.0])

    fig, ax = plt.subplots(figsize=(8, 5))
    box2 = ax.boxplot(recall_by_persona, tick_labels=[p.capitalize() for p in personas], patch_artist=True)
    for patch in box2["boxes"]:
        patch.set_facecolor("#2b5c8f")
        patch.set_alpha(0.7)
    ax.set_title("Red Flag Recall Distribution by Persona", fontsize=12, fontweight="bold")
    ax.set_ylabel("Planted Red Flag Recall Rate (0.0 - 1.0)", fontsize=10)
    ax.set_ylim(-0.05, 1.1)
    ax.grid(axis="y", linestyle="--", alpha=0.5)

    p2_path = plot_path / "red_flag_recall_by_persona.png"
    plt.tight_layout()
    plt.savefig(p2_path, dpi=200)
    plt.close()
    generated_plots.append(p2_path)

    # -------------------------------------------------------------------------
    # Plot 3: Tokens Distribution by Messaging Mode
    # -------------------------------------------------------------------------
    bb_tokens = [int(r["tokens"]) for r in rows if r["mode"] == "blackboard"]
    p2p_tokens = [int(r["tokens"]) for r in rows if r["mode"] == "hybrid_p2p"]

    fig, ax = plt.subplots(figsize=(7, 5))
    box3 = ax.boxplot([bb_tokens, p2p_tokens], tick_labels=["Blackboard", "Hybrid P2P"], patch_artist=True)
    box3["boxes"][0].set_facecolor("#C44E52")
    box3["boxes"][1].set_facecolor("#8172B3")
    for patch in box3["boxes"]:
        patch.set_alpha(0.7)
    ax.set_title("Token Consumption Distribution by Mode", fontsize=12, fontweight="bold")
    ax.set_ylabel("Total Tokens per Run", fontsize=10)
    ax.grid(axis="y", linestyle="--", alpha=0.5)

    p3_path = plot_path / "tokens_per_run_by_mode.png"
    plt.tight_layout()
    plt.savefig(p3_path, dpi=200)
    plt.close()
    generated_plots.append(p3_path)

    # -------------------------------------------------------------------------
    # Plot 4: Injection Ablation Bar Chart (Guardrails ON vs OFF)
    # -------------------------------------------------------------------------
    fig, ax = plt.subplots(figsize=(7, 5))
    # Filter injecting runs
    inject_runs = [r for r in rows if r["persona"] == "injecting"]
    g_on_runs = [r for r in inject_runs if int(r.get("guardrail_events", 0)) > 0]
    g_off_runs = [r for r in inject_runs if int(r.get("guardrail_events", 0)) == 0]

    on_success = sum(1 for r in g_on_runs if r.get("injection_succeeded") in (True, "True", "true"))
    off_success = sum(1 for r in g_off_runs if r.get("injection_succeeded") in (True, "True", "true"))

    rate_on = (on_success / len(g_on_runs) * 100.0) if g_on_runs else 0.0
    rate_off = (off_success / len(g_off_runs) * 100.0) if g_off_runs else 0.0

    bars = ax.bar(
        ["Guardrails Active\n(Production Default)", "Guardrails Disabled\n(Ablation Study)"],
        [rate_on, rate_off],
        color=["#2ca02c", "#d62728"],
        alpha=0.75,
        width=0.45,
    )
    ax.set_title("Prompt Injection Attack Success Rate", fontsize=12, fontweight="bold")
    ax.set_ylabel("Injection Success Rate (%)", fontsize=10)
    ax.set_ylim(0, 100)
    ax.grid(axis="y", linestyle="--", alpha=0.5)

    for bar in bars:
        h = bar.get_height()
        ax.text(bar.get_x() + bar.get_width() / 2, h + 2, f"{h:.1f}%", ha="center", fontweight="bold")

    p4_path = plot_path / "injection_ablation_bar_chart.png"
    plt.tight_layout()
    plt.savefig(p4_path, dpi=200)
    plt.close()
    generated_plots.append(p4_path)

    # -------------------------------------------------------------------------
    # Heatmap Data Aggregation from Traces
    # -------------------------------------------------------------------------
    agents = [
        "adk.gateway",
        "adk.extractor",
        "crewai.identity_verifier",
        "crewai.sanctions_screener",
        "crewai.media_analyst",
        "crewai.ubo_analyst",
        "adk.risk_scorer",
        "adk.reviewer",
    ]
    phases = ["intake", "verification", "screening", "risk", "review"]
    step_types = ["model", "tool", "guardrail", "a2a", "blackboard"]

    lat_matrix = np.zeros((len(agents), len(phases)))
    lat_counts = np.zeros((len(agents), len(phases)))

    step_matrix = np.zeros((len(agents), len(step_types)))
    error_counts = np.zeros((len(agents), 2))  # [Errors, Guardrail Triggers]

    for run_dir in res_path.iterdir():
        tr_file = run_dir / "traces.json"
        if not tr_file.exists():
            continue
        try:
            with open(tr_file, encoding="utf-8") as f_tr:
                traces = json.load(f_tr)
            for t in traces:
                ag = t.get("agent_id")
                ph = t.get("phase")
                st = t.get("step_type")
                lat = float(t.get("latency_ms", 0.0))

                if ag in agents and ph in phases:
                    ai = agents.index(ag)
                    pi = phases.index(ph)
                    lat_matrix[ai, pi] += lat
                    lat_counts[ai, pi] += 1

                if ag in agents and st in step_types:
                    ai = agents.index(ag)
                    si = step_types.index(st)
                    step_matrix[ai, si] += 1

                if ag in agents and t.get("error"):
                    ai = agents.index(ag)
                    error_counts[ai, 0] += 1
        except (OSError, json.JSONDecodeError, KeyError):
            continue

    # Plot 5: Agent x Phase Latency Heatmap
    avg_lat_matrix = np.divide(lat_matrix, lat_counts, out=np.zeros_like(lat_matrix), where=lat_counts != 0)
    fig, ax = plt.subplots(figsize=(9, 6))
    cax = ax.matshow(avg_lat_matrix, cmap="YlGnBu", aspect="auto")
    fig.colorbar(cax)
    ax.set_xticks(range(len(phases)))
    ax.set_yticks(range(len(agents)))
    ax.set_xticklabels([p.capitalize() for p in phases], fontsize=10)
    ax.set_yticklabels(agents, fontsize=10)
    ax.set_title("Heatmap: Mean Latency (ms) by Agent and Phase", fontsize=12, fontweight="bold", pad=20)

    for i in range(len(agents)):
        for j in range(len(phases)):
            val = avg_lat_matrix[i, j]
            ax.text(j, i, f"{val:.0f}", ha="center", va="center", color="black" if val < 200 else "white", fontsize=8)

    p5_path = plot_path / "heatmap_agent_phase_latency.png"
    plt.tight_layout()
    plt.savefig(p5_path, dpi=200)
    plt.close()
    generated_plots.append(p5_path)

    # Plot 6: Agent x Step Type Heatmap
    fig, ax = plt.subplots(figsize=(9, 6))
    cax6 = ax.matshow(step_matrix, cmap="Purples", aspect="auto")
    fig.colorbar(cax6)
    ax.set_xticks(range(len(step_types)))
    ax.set_yticks(range(len(agents)))
    ax.set_xticklabels([s.upper() for s in step_types], fontsize=10)
    ax.set_yticklabels(agents, fontsize=10)
    ax.set_title("Heatmap: Step Type Invocations by Agent", fontsize=12, fontweight="bold", pad=20)

    for i in range(len(agents)):
        for j in range(len(step_types)):
            val = int(step_matrix[i, j])
            ax.text(j, i, str(val), ha="center", va="center", color="black" if val < 30 else "white", fontsize=8)

    p6_path = plot_path / "heatmap_agent_step_type.png"
    plt.tight_layout()
    plt.savefig(p6_path, dpi=200)
    plt.close()
    generated_plots.append(p6_path)

    # Plot 7: Agent x Errors & Guardrail Triggers Heatmap
    # Aggregate guardrail events
    for run_dir in res_path.iterdir():
        rep_file = run_dir / "report.json"
        if rep_file.exists():
            try:
                with open(rep_file, encoding="utf-8") as f_r:
                    rep_obj = json.load(f_r)
                    for ag_m in rep_obj.get("per_agent", []):
                        ag_name = ag_m.get("agent_id")
                        if ag_name in agents:
                            ai = agents.index(ag_name)
                            error_counts[ai, 1] += ag_m.get("guardrail_triggers", 0)
            except (OSError, json.JSONDecodeError, KeyError):
                pass

    fig, ax = plt.subplots(figsize=(7, 6))
    cax7 = ax.matshow(error_counts, cmap="Reds", aspect="auto")
    fig.colorbar(cax7)
    ax.set_xticks([0, 1])
    ax.set_yticks(range(len(agents)))
    ax.set_xticklabels(["Runtime Errors", "Guardrail Triggers"], fontsize=10)
    ax.set_yticklabels(agents, fontsize=10)
    ax.set_title("Heatmap: Errors & Guardrail Triggers by Agent", fontsize=12, fontweight="bold", pad=20)

    for i in range(len(agents)):
        for j in range(2):
            val = int(error_counts[i, j])
            ax.text(j, i, str(val), ha="center", va="center", color="black" if val < 10 else "white", fontsize=8)

    p7_path = plot_path / "heatmap_agent_errors_guardrails.png"
    plt.tight_layout()
    plt.savefig(p7_path, dpi=200)
    plt.close()
    generated_plots.append(p7_path)

    # -------------------------------------------------------------------------
    # Statistical Hypotheses Testing: Mann-Whitney U Test
    # -------------------------------------------------------------------------
    stat_report = []
    if seq_runtimes and par_runtimes:
        u_stat_pat, p_val_pat = stats.mannwhitneyu(seq_runtimes, par_runtimes, alternative="two-sided")
        stat_report.append({
            "comparison": "Pattern Runtime (Sequential vs Parallel)",
            "u_stat": float(u_stat_pat),
            "p_value": float(p_val_pat),
            "significant_at_05": bool(p_val_pat < 0.05),
            "seq_mean": float(np.mean(seq_runtimes)),
            "par_mean": float(np.mean(par_runtimes)),
        })

    if bb_runtimes and p2p_runtimes:
        u_stat_mode, p_val_mode = stats.mannwhitneyu(bb_runtimes, p2p_runtimes, alternative="two-sided")
        stat_report.append({
            "comparison": "Mode Runtime (Blackboard vs Hybrid P2P)",
            "u_stat": float(u_stat_mode),
            "p_value": float(p_val_mode),
            "significant_at_05": bool(p_val_mode < 0.05),
            "bb_mean": float(np.mean(bb_runtimes)),
            "p2p_mean": float(np.mean(p2p_runtimes)),
        })

    with open(plot_path / "statistical_tests.json", "w", encoding="utf-8") as f_st:
        json.dump(stat_report, f_st, indent=2)

    print(f"Generated {len(generated_plots)} evaluation plots in {plot_path}")
    return generated_plots


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate benchmark evaluation plots")
    parser.add_argument("--results", default="results", help="Directory containing run results")
    parser.add_argument("--metrics", default="results/metrics.csv", help="Path to metrics.csv")
    parser.add_argument("--out", default="results/plots", help="Directory to save generated PNG plots")
    args = parser.parse_args()

    generate_plots(results_dir=args.results, metrics_csv=args.metrics, plots_dir=args.out)


if __name__ == "__main__":
    main()
