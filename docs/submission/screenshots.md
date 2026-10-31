# OnboardIQ UI Screenshot Guide for Report & Presentation

This guide lists the screenshots to capture from the live Streamlit console (`http://localhost:8501`) for inclusion in the final course submission report (`docs/submission/final_report.md`) and presentation slides.

---

### Screenshot 1: Client Application & Multi-Agent Execution Portal
- **Navigation Menu:** `📋 Client Application`
- **Configuration to Display:**
  - Case: `case_008: Nordic Import Export LLP (COMPANY)`
  - Messaging Architecture: `Central Blackboard`
  - Orchestration Pattern: `Parallel ThreadPool Dispatch`
  - Persona: `Impatient Persona`
  - Reasoning: `ReAct (Thought-Action-Observation)`
  - Security Perimeter Guardrails: Checked
- **What to Capture:** The form parameters, supporting documents preview, and the resulting **Outcome Banner** showing `DECISION: ESCALATE_TO_HUMAN`, Risk Tier `HIGH`, and the automated rationale citing the sanctions near-match beneficial owner.
- **Report Section:** Section 3 (Implementation) & Section 4 (Agentic Design Patterns).

---

### Screenshot 2: Live Zoned Blackboard Inspector (PII Masked)
- **Navigation Menu:** `🧠 Live Blackboard`
- **Run to Select:** `ui_case_008_bl_par`
- **What to Capture:**
  - `Intake Zone` tab: Show the masked applicant profile (`display_name: "Nordic Import Export LLP"`, `id_last4: "****"`, raw PII vault excluded).
  - `Screening Zone` tab: Show the populated `hits` table (OFAC match on Viktor Darkovich) and `red_flags` table (`sanctions_hit`).
  - Active version counter (`v11+`) and phase indicator (`REVIEW`).
- **Report Section:** Section 2 (System Architecture: Zoned Blackboard) & Section 6 (Security & PII Segregation).

---

### Screenshot 3: Compliance Officer Console (Human-in-the-Loop)
- **Navigation Menu:** `⚖️ Compliance Officer Console`
- **Case to Select:** `ui_case_008_bl_par` (Escalated case)
- **What to Capture:** The officer review panel showing:
  - Automated system risk score (85/100) and rationale.
  - Compliance Officer Name input field (`Senior Compliance Officer`).
  - Justification & Legal Audit notes (`Confirmed high risk match on international watchlist`).
  - The two human decision buttons (`Human Approve (Override)` and `Human Confirm Reject`).
- **Report Section:** Section 4 (Human-in-the-Loop Governance & Course Criterion 8).

---

### Screenshot 4: Evaluation & Analytics Dashboard
- **Navigation Menu:** `📊 Evaluation & Analytics`
- **What to Capture:**
  - Top 4 KPI summary metric cards: `Evaluated Sweep Runs: 58`, `Decision Accuracy: 75.9%`, `Tier Agreement: 75.9%`, `Mean Latency: 0.228s`.
  - The interactive benchmark metrics table (`results/metrics.csv`).
  - Side-by-side empirical benchmark figures (`runtime_and_cost_boxplots.png`, `red_flag_recall_by_persona.png`, `heatmap_agent_phase_latency.png`).
- **Report Section:** Section 5 (Empirical Evaluation: 40+ Runs, Runtime, Cost & Heatmaps).

---

### Screenshot 5: OpenTelemetry Distributed Tracing & Provenance Inspector
- **Navigation Menu:** `🔍 OpenTelemetry Provenance`
- **Run to Select:** Any active run
- **What to Capture:**
  - 128-bit deterministic Trace ID (`0x...`).
  - Total captured spans count.
  - Verification badge (`PROVENANCE AUDIT VERIFIED`).
  - Traced agents, FastMCP tools called, guardrail events triggered, and the span hierarchy list.
- **Report Section:** Section 7 (Observability, Auditability & Provenance: Criterion 9).

---

### How to Run the App
```bash
# In project root:
.venv\Scripts\streamlit run src/onboardiq/ui/app.py --server.port=8501
```
Open your browser at `http://localhost:8501`.

