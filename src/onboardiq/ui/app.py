"""OnboardIQ Streamlit Web Application.

Per docs/02_PRD.md and docs/06_IMPLEMENTATION_PLAN.md T31:
- Client application form (select case, persona, pattern, mode)
- Live zoned blackboard inspector with masked PII
- Compliance officer review console with human override
- Evaluation metrics and visualization dashboard
"""

from __future__ import annotations

import csv
from pathlib import Path

import streamlit as st

from onboardiq.agents.adk.orchestrator import Orchestrator
from onboardiq.blackboard.client import BlackboardClient
from onboardiq.blackboard.service import app as fastapi_app
from onboardiq.blackboard.store import SQLiteBlackboardStore
from onboardiq.schema import (
    LabelledCase,
    Mode,
    OnboardingReport,
    Pattern,
    Persona,
    Reasoning,
    RunConfig,
)

# Page configuration
st.set_page_config(
    page_title="OnboardIQ - Multi-Agent KYC/AML Platform",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS for polished fintech feel
st.markdown(
    """
    <style>
    .main-header { font-size: 2.2rem; font-weight: 700; color: #1E3A8A; margin-bottom: 0.2rem; }
    .sub-header { font-size: 1.05rem; color: #4B5563; margin-bottom: 1.5rem; }
    .badge-approve { background-color: #DEF7EC; color: #03543F; padding: 4px 12px; border-radius: 9999px; font-weight: 700; }
    .badge-edd { background-color: #FEF08A; color: #854D0E; padding: 4px 12px; border-radius: 9999px; font-weight: 700; }
    .badge-escalate { background-color: #FEE2E2; color: #991B1B; padding: 4px 12px; border-radius: 9999px; font-weight: 700; }
    .zone-card { background-color: #F9FAFB; border: 1px solid #E5E7EB; border-radius: 8px; padding: 16px; margin-bottom: 12px; }
    </style>
    """,
    unsafe_allow_html=True,
)


def get_shared_client() -> BlackboardClient:
    """Get persistent BlackboardClient bound to the in-memory or SQLite store."""
    if "board_client" not in st.session_state:
        if not hasattr(fastapi_app.state, "store"):
            fastapi_app.state.store = SQLiteBlackboardStore(db_path=":memory:")
        st.session_state.board_client = BlackboardClient(base_url="http://testserver", app=fastapi_app)
    return st.session_state.board_client


def load_cases() -> dict[str, LabelledCase]:
    """Load all benchmark cases from data/cases/."""
    cases: dict[str, LabelledCase] = {}
    cases_dir = Path("data/cases")
    if cases_dir.exists():
        for f in sorted(cases_dir.glob("case_*.json")):
            with open(f, encoding="utf-8") as fp:
                case = LabelledCase.model_validate_json(fp.read())
                cases[case.case_id] = case
    return cases


# Sidebar Navigation
st.sidebar.markdown("## 🛡️ OnboardIQ")
st.sidebar.markdown("**Agentic KYC/AML System**")
nav = st.sidebar.radio(
    "Navigation",
    [
        "📋 Client Application",
        "🧠 Live Blackboard",
        "⚖️ Compliance Officer Console",
        "📊 Evaluation & Analytics",
    ],
)

client = get_shared_client()
all_cases = load_cases()

if "recent_reports" not in st.session_state:
    st.session_state.recent_reports = {}
if "last_run_id" not in st.session_state:
    st.session_state.last_run_id = None

# =========================================================================
# View 1: Client Application Form & Onboarding Run
# =========================================================================
if nav == "📋 Client Application":
    st.markdown('<div class="main-header">Client Onboarding Portal</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="sub-header">Submit applicant credentials through the Security Gateway to trigger multi-agent screening.</div>',
        unsafe_allow_html=True,
    )

    col1, col2 = st.columns([1, 1])

    with col1:
        st.markdown("### 1. Select Applicant Case")
        case_options = {
            cid: f"{cid}: {c.declared_name} ({c.client_type.value.title()})"
            for cid, c in all_cases.items()
        }
        selected_cid = st.selectbox("Benchmark Applicant", list(case_options.keys()), format_func=lambda x: case_options[x])
        selected_case = all_cases[selected_cid]

        st.info(
            f"**Applicant:** {selected_case.declared_name}  \n"
            f"**Country:** {selected_case.declared_country} | **Type:** {selected_case.client_type.value.title()}  \n"
            f"**Source of Funds:** {selected_case.declared_source_of_funds}  \n"
            f"**Expected Volume:** ₹{selected_case.expected_monthly_volume_inr:,.0f}/month"
        )

        st.markdown("### 2. Runtime Execution Configuration")
        c_mode = st.selectbox("Messaging Mode", ["blackboard", "hybrid_p2p"], index=0)
        c_pattern = st.selectbox("Execution Pattern", ["sequential", "parallel"], index=0)
        c_persona = st.selectbox("Applicant Persona", ["cooperative", "impatient", "abusive", "forger", "injecting"], index=0)
        c_guardrails = st.checkbox("Enable Security Guardrails", value=True)

        run_btn = st.button("🚀 Submit Application & Run Onboarding", type="primary", use_container_width=True)

    with col2:
        st.markdown("### 3. Declared Documents")
        if selected_case.documents:
            for doc_path in selected_case.documents:
                p = Path(doc_path)
                st.caption(f"Document File: `{p.name}`")
                if p.exists() and p.suffix.lower() in (".png", ".jpg", ".jpeg"):
                    st.image(str(p), width=320)
        else:
            st.info("No documents declared for this case.")

        if selected_case.ownership_chart:
            st.markdown("### Corporate Ownership Chart")
            st.json(selected_case.ownership_chart)

    if run_btn:
        with st.spinner("Executing OnboardIQ agents across extraction, screening, and risk scoring..."):
            orch = Orchestrator()
            run_id = f"ui_{selected_case.case_id}_{c_mode[:2]}_{c_pattern[:3]}"

            config = RunConfig(
                case_id=selected_case.case_id,
                mode=Mode(c_mode),
                pattern=Pattern(c_pattern),
                persona=Persona(c_persona),
                reasoning=Reasoning.PLAIN,
                guardrails_enabled=c_guardrails,
            )

            report = orch.run_case(
                case=selected_case,
                board_client=client,
                run_id=run_id,
                config=config,
            )

            st.session_state.recent_reports[run_id] = report
            st.session_state.last_run_id = run_id
            st.success(f"Onboarding execution completed for `{run_id}` in {report.total_runtime_s:.2f}s!")

    # Display Report if available
    active_run = st.session_state.last_run_id
    if active_run and active_run in st.session_state.recent_reports:
        rep: OnboardingReport = st.session_state.recent_reports[active_run]

        st.markdown("---")
        st.markdown(f"## 📑 Onboarding Report: `{rep.run_id}`")

        # KPI Badges
        kpi1, kpi2, kpi3, kpi4, kpi5 = st.columns(5)
        with kpi1:
            st.metric("Risk Score", f"{rep.risk_score:.0f} / 100")
        with kpi2:
            st.metric("Risk Tier", rep.risk_tier.value.upper())
        with kpi3:
            st.metric("Red Flags", len(rep.red_flags))
        with kpi4:
            st.metric("Sanctions Hits", rep.sanctions_or_pep_hits)
        with kpi5:
            st.metric("Execution Time", f"{rep.total_runtime_s:.3f}s")

        # Decision Alert
        dec_val = rep.decision.value
        if dec_val == "approve":
            st.success(f"### FINAL DECISION: {dec_val.upper()}")
        elif dec_val == "approve_with_enhanced_monitoring":
            st.warning(f"### FINAL DECISION: {dec_val.upper()} (Enhanced Monitoring Required)")
        else:
            st.error(f"### FINAL DECISION: {dec_val.upper()} (Escalated to Compliance Officer)")

        st.markdown("#### Rationale")
        st.info(rep.decision_rationale)

        with st.expander("🔍 View Resolvable Evidence Trail"):
            for ev in rep.evidence_trail:
                st.code(f"ID: {ev.evidence_id} | Agent: {ev.agent_id} | Tool: {ev.tool or 'N/A'} | Record: {ev.record_id or 'N/A'}")

        with st.expander("⚡ Agent Execution Metrics & Telemetry"):
            metrics_table = [
                {
                    "Agent": m.agent_id,
                    "Latency (ms)": m.total_latency_ms,
                    "Tokens": m.tokens,
                    "Cost ($)": f"${m.cost_usd:.6f}",
                    "Tool Calls": m.tool_calls,
                }
                for m in rep.per_agent
            ]
            st.dataframe(metrics_table, use_container_width=True)


# =========================================================================
# View 2: Live Zoned Blackboard Inspector
# =========================================================================
elif nav == "🧠 Live Blackboard":
    st.markdown('<div class="main-header">Zoned Blackboard Inspector</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="sub-header">Inspect typed, versioned state zones in real-time. Raw PII is automatically masked.</div>',
        unsafe_allow_html=True,
    )

    run_list = list(st.session_state.recent_reports.keys())
    if not run_list:
        st.warning("No runs executed yet in this session. Go to '📋 Client Application' and run a case first!")
    else:
        chosen_run = st.selectbox("Select Blackboard Run", run_list)
        board = client.get_run(chosen_run, agent_id="adk.orchestrator")

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Run ID", board.run_id)
        m2.metric("Version (Audit Log)", board.version)
        m3.metric("Messaging Mode", board.mode.value)
        m4.metric("Execution Pattern", board.pattern.value)

        tab_intake, tab_verif, tab_screen, tab_risk, tab_review, tab_sys = st.tabs(
            ["📥 Intake Zone", "🔍 Verification", "🛡️ Screening & UBO", "⚠️ Risk Zone", "📝 Review Zone", "⚙️ System Traces"]
        )

        with tab_intake:
            st.markdown("#### Masked Client Profile (Safe for Agents)")
            st.json(board.intake.profile.model_dump())
            st.markdown("#### Extracted Documents")
            st.json([d.model_dump() for d in board.intake.documents])
            st.markdown("#### Restricted PII Vault (Masked)")
            st.json({
                "raw_name": board.pii_vault.raw_name,
                "address": board.pii_vault.address,
                "dob": board.pii_vault.dob,
                "status": "Restricted Access Enforced by Access Control Matrix",
            })

        with tab_verif:
            st.markdown("#### Identity Verification Checks")
            if board.verification.checks:
                for chk in board.verification.checks:
                    st.write(f"- **{chk.check_type}**: {'✅ PASSED' if chk.passed else '❌ FAILED'} (Similarity: {chk.similarity:.2f})")
                    st.caption(f"Detail: {chk.detail} | Evidence: `{chk.evidence.evidence_id}`")
            else:
                st.write("No verification checks recorded.")

        with tab_screen:
            st.markdown("#### Sanctions & PEP Hits")
            if board.screening.hits:
                for hit in board.screening.hits:
                    st.error(f"🚨 Hit: `{hit.matched_name}` on {hit.list_name} (Score: {hit.match_score:.2f}, Disposition: {hit.disposition})")
                    st.caption(f"Reasoning: {hit.reasoning}")
            else:
                st.success("No sanctions or PEP matches found.")

            st.markdown("#### Corporate UBO Graph Entries")
            if board.screening.ubos:
                for u in board.screening.ubos:
                    st.write(f"🏢 **{u.owner_name}**: {u.ownership_pct}% | Path: `{' -> '.join(u.path)}` | Verified: {'✅' if u.verified else '❌'}")
            else:
                st.info("No corporate UBO entries for this case.")

            st.markdown("#### Red Flags Raised")
            if board.screening.red_flags:
                for rf in board.screening.red_flags:
                    st.warning(f"🚩 **{rf.flag_type.upper()}** (Severity: {rf.severity}) | Raised by: `{rf.raised_by}`")
            else:
                st.success("Zero red flags active.")

        with tab_risk:
            st.markdown("#### Risk Assessment")
            if board.risk.assessment:
                st.json(board.risk.assessment.model_dump())
            if board.risk.draft:
                st.markdown("#### Decision Draft")
                st.json(board.risk.draft.model_dump())

        with tab_review:
            st.markdown("#### Review & Challenges")
            if board.review.final_decision:
                st.success(f"Final Decision Recorded: `{board.review.final_decision}`")
            if board.review.human_override:
                st.info(f"Human Override: {board.review.human_override}")
            else:
                st.write("No human override currently recorded.")

        with tab_sys:
            st.markdown("#### Step Traces")
            st.dataframe([t.model_dump() for t in board.system.traces], use_container_width=True)
            st.markdown("#### Guardrail Events")
            st.dataframe([g.model_dump() for g in board.system.guardrail_events], use_container_width=True)


# =========================================================================
# View 3: Compliance Officer Console (Human-in-the-Loop)
# =========================================================================
elif nav == "⚖️ Compliance Officer Console":
    st.markdown('<div class="main-header">Compliance Officer Console</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="sub-header">Review high-risk escalated cases and record audited human override decisions.</div>',
        unsafe_allow_html=True,
    )

    escalated_runs = [
        r_id
        for r_id, rep in st.session_state.recent_reports.items()
        if rep.decision.value == "escalate_to_human"
    ]

    if not escalated_runs:
        st.success("No pending escalated cases require review right now! Run `case_008` (Sanctioned Owner) or `case_006` from the Client Portal to test human escalation.")
    else:
        selected_esc_run = st.selectbox("Select Escalated Case for Human Review", escalated_runs)
        esc_report: OnboardingReport = st.session_state.recent_reports[selected_esc_run]

        st.warning(f"### Action Required: `{selected_esc_run}` ({esc_report.case_id})")

        c1, c2 = st.columns(2)
        with c1:
            st.markdown("#### Case Summary")
            st.write(f"- **Risk Tier**: `{esc_report.risk_tier.value.upper()}` (Score: {esc_report.risk_score:.0f}/100)")
            st.write(f"- **Sanctions Hits**: {esc_report.sanctions_or_pep_hits}")
            st.write(f"- **Red Flags**: {len(esc_report.red_flags)}")
            st.markdown("#### Automated System Rationale")
            st.info(esc_report.decision_rationale)

        with c2:
            st.markdown("#### Human Officer Decision")
            officer_name = st.text_input("Compliance Officer Name", value="Senior Compliance Officer")
            officer_notes = st.text_area("Justification & Legal Audit Notes", "Confirmed high risk match on international watchlist.")

            btn_col1, btn_col2 = st.columns(2)
            with btn_col1:
                if st.button("✅ Human Approve (Override)", type="secondary", use_container_width=True):
                    # Write human override to review zone
                    board = client.get_run(selected_esc_run, agent_id="adk.orchestrator")
                    override_payload = {
                        "human_override": {
                            "officer": officer_name,
                            "decision": "approved_by_human",
                            "notes": officer_notes,
                        },
                        "final_decision": "approve",
                    }
                    client.append_event_with_retry(
                        run_id=selected_esc_run,
                        zone="review",
                        payload=override_payload,
                        expected_version=board.version,
                        op="update",
                        agent_id="adk.reviewer",
                    )
                    st.success(f"Case {selected_esc_run} successfully approved by {officer_name}!")
            with btn_col2:
                if st.button("❌ Human Confirm Reject", type="primary", use_container_width=True):
                    board = client.get_run(selected_esc_run, agent_id="adk.orchestrator")
                    override_payload = {
                        "human_override": {
                            "officer": officer_name,
                            "decision": "rejected_by_human",
                            "notes": officer_notes,
                        },
                        "final_decision": "reject",
                    }
                    client.append_event_with_retry(
                        run_id=selected_esc_run,
                        zone="review",
                        payload=override_payload,
                        expected_version=board.version,
                        op="update",
                        agent_id="adk.reviewer",
                    )
                    st.error(f"Case {selected_esc_run} rejected by {officer_name} and logged to audit trail.")


# =========================================================================
# View 4: Evaluation & Analytics Dashboard
# =========================================================================
elif nav == "📊 Evaluation & Analytics":
    st.markdown('<div class="main-header">Evaluation & Performance Analytics</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="sub-header">Benchmark sweep metrics, latency distributions, and agent phase heatmaps.</div>',
        unsafe_allow_html=True,
    )

    metrics_csv_path = Path("results/metrics.csv")
    if metrics_csv_path.exists():
        rows = []
        with open(metrics_csv_path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        if rows:
            t_runs = len(rows)
            t_acc = sum(1 for r in rows if r["decision_correct"] == "True") / t_runs * 100.0
            t_tier_acc = sum(1 for r in rows if r["tier_correct"] == "True") / t_runs * 100.0
            t_avg_lat = sum(float(r["runtime_s"]) for r in rows) / t_runs

            k1, k2, k3, k4 = st.columns(4)
            k1.metric("Evaluated Sweep Runs", t_runs)
            k2.metric("Decision Accuracy", f"{t_acc:.1f}%")
            k3.metric("Tier Agreement", f"{t_tier_acc:.1f}%")
            k4.metric("Mean Latency", f"{t_avg_lat:.3f}s")

            st.markdown("### Benchmark Metrics Table (`results/metrics.csv`)")
            st.dataframe(rows, use_container_width=True)
    else:
        st.warning("Run the evaluation runner first using `python -m onboardiq.eval.runner`!")

    st.markdown("### Benchmark Visualizations")
    col_p1, col_p2 = st.columns(2)

    plot_box = Path("results/plots/runtime_by_pattern.png")
    plot_heat = Path("results/plots/agent_phase_heatmap.png")

    with col_p1:
        if plot_box.exists():
            st.image(str(plot_box), caption="Runtime Spread: Sequential vs Parallel Patterns", use_container_width=True)
    with col_p2:
        if plot_heat.exists():
            st.image(str(plot_heat), caption="Agent x Phase Latency Heatmap", use_container_width=True)

