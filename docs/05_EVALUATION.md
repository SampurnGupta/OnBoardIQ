# 05 - Evaluation Plan

Covers course criterion 10: end-to-end performance, cost and runtime over 40 or more runs, boxplots, and a dataset to report against.

## 1. Dataset

All data is synthetic. Generate with `src/onboardiq/eval/dataset_gen.py` using a fixed seed.

**Size:** 20 to 24 base cases (about 14 individuals, 8 companies), each with ground truth. Persona variants multiply these into runs.

**Case file** (`data/cases/case_001.json`), validated by a Pydantic `LabelledCase`:

```json
{
  "case_id": "case_001",
  "client_type": "individual",
  "applicant": { "declared_name": "...", "declared_dob": "...", "declared_country": "...",
                 "declared_address": "...", "declared_source_of_funds": "...",
                 "expected_monthly_volume_inr": 50000 },
  "documents": ["data/docs/case_001_pan.png", "data/docs/case_001_address.pdf"],
  "ownership_chart": null,
  "ground_truth": {
    "expected_tier": "low",
    "expected_decision": "approve",
    "planted_flags": [],
    "is_namesake_false_positive": false
  }
}
```

**Planted flag types:** `identity_mismatch`, `doc_tampering`, `sanctions_hit` (perturbed public-list name), `pep`, `adverse_media`, `opaque_ownership`, `inconsistent_funds`.

**Composition (target):**

| Group | Count | Purpose |
|---|---|---|
| Clean individuals | 6 | Baseline, false-positive measurement |
| Namesake false positives | 3 | Similar to a listed name but clearly different person |
| Planted single flags | 8 | Recall per flag type |
| Multi-flag high risk | 3 | Escalation behaviour |
| Companies (clean, opaque, sanctioned owner) | 6 | UBO path |

**Supporting data:** public OFAC and UN list names (downloaded by you), a small PEP list you assemble from public sources, a mock registry SQLite DB with valid synthetic ID records, a short KYC policy `data/policy.md`, and a small news corpus for reproducible runs.

**Risk model training data:** a separate synthetic set (a few hundred rows) generated from rules plus noise, with features such as country risk, occupation risk, volume, number of flags, screening score, tamper score. Keep it separate from the evaluation cases.

## 2. Experiment grid

| Factor | Levels |
|---|---|
| Messaging mode | `blackboard`, `hybrid_p2p` |
| Pattern | `sequential`, `parallel` |
| Persona | `cooperative`, `impatient`, `abusive`, `forger`, `injecting` |

2 x 2 x 5 = 20 cells x 2 cases per cell = **40 runs** minimum. If budget allows, 3 cases per cell = 60 runs.

**Side studies**
- **Reasoning style:** ReAct vs plain prompts on the cooperative persona, about 20 runs.
- **Guardrail ablation:** injecting and abusive personas, guardrails on vs off, about 20 runs.
- **Repeats:** rerun a handful of identical configurations to estimate variance.

Randomise run order and record `seed`, model name and timestamp per run.

## 3. Metrics

| Group | Metric | How computed |
|---|---|---|
| Decision quality | Decision accuracy | report decision equals expected decision (escalate counts as correct for expected escalate) |
| | Tier agreement | predicted tier equals expected tier; also report adjacent-tier tolerance |
| | Red-flag recall / precision | planted vs raised flags by type |
| | Sanctions-hit recall | planted sanctions cases escalated |
| | False-positive rate | clean or namesake cases wrongly escalated or flagged |
| Efficiency | Runtime (s), tokens, cost (USD) | from `StepTrace` sums |
| | RFI rounds, reviewer loops | counts from board |
| Safety | Toxic inputs blocked | guardrail events |
| | Injection success | tier or decision differs from the clean twin, or injected instruction obeyed |
| | PII leaks | leak detector on tool inputs, messages and report |
| | Access denials, schema violations caught | guardrail events |
| Reliability | Errors per run, retries | traces |

## 4. Outputs and plots (`eval/plots.py`)

1. Boxplots of runtime and cost: Sequential vs Parallel; Blackboard vs Hybrid P2P.
2. Boxplot of red-flag recall by persona.
3. Boxplot of tokens per run by mode.
4. Bar chart: injection success rate, guardrails off vs on.
5. Heatmap agent x phase (latency).
6. Heatmap agent x step type (count or tokens).
7. Heatmap agent x error and guardrail triggers.
8. Summary table: mean, median, standard deviation, per cell.

Statistics: Mann-Whitney U test or bootstrap confidence intervals for key comparisons (mode, pattern). State sample sizes honestly; with 40 runs treat results as indicative.

## 5. Runner design

- `eval/runner.py --grid configs/grid.yaml --out results/` runs each configuration, catching exceptions so one failure does not stop the sweep.
- Each run saves `report.json`, `traces.json` and the final board snapshot under `results/{run_id}/`.
- `eval/metrics.py` loads results and the ground truth, computes the metrics table to `results/metrics.csv`.
- `eval/plots.py` reads `metrics.csv` and traces and writes PNG files to `results/plots/`.
- Cache deterministic tool results to cut cost; never cache LLM calls across configurations being compared.

## 6. Reporting checklist

- Dataset description and composition table.
- Grid definition and number of runs actually completed.
- Metric definitions.
- Plots with a one-line takeaway each.
- Limitations: synthetic data, small sample, model-specific results.
