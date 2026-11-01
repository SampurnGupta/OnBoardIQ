"""OnboardIQ Streamlit Web Application.

Per docs/02_PRD.md and docs/06_IMPLEMENTATION_PLAN.md T31:
- Client application form (select case, persona, pattern, mode, reasoning)
- Live zoned blackboard inspector with masked PII
- Compliance officer review console with human override
- Evaluation metrics and visualization dashboard (all 7 benchmark plots)
- OpenTelemetry Distributed Tracing & Audit Provenance Inspector
"""

from __future__ import annotations

import csv
from pathlib import Path

import streamlit as st

from onboardiq.agents.adk.orchestrator import Orchestrator
from onboardiq.blackboard.client import BlackboardClient
from onboardiq.blackboard.service import app as fastapi_app
from onboardiq.blackboard.store import SQLiteBlackboardStore
from onboardiq.guardrails.persona_injector import inject_persona
from onboardiq.schema import (
    LabelledCase,
    Mode,
    OnboardingReport,
    Pattern,
    Persona,
    Reasoning,
    RunConfig,
)
from onboardiq.telemetry.tracing import get_provenance_summary

# Page configuration
st.set_page_config(
    page_title="OnboardIQ - Multi-Agent KYC/AML Platform",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS for fintech feel
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
    """Load all 24 benchmark cases from data/cases/."""
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
st.sidebar.markdown("**Multi-Agent KYC/AML System**")
st.sidebar.markdown("*(CSE3101 Agentic AI Coursework)*")
nav = st.sidebar.radio(
    "Navigation Menu",
    [
        "📋 Client Application",
        "🧠 Live Blackboard",
        "⚖️ Compliance Officer Console",
        "📊 Evaluation & Analytics",
        "🔍 OpenTelemetry Provenance",
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
        '<div class="sub-header">Submit corporate or individual onboarding dossiers across agent frameworks.</div>',
        unsafe_allow_html=True,
    )

    col_form, col_summary = st.columns([1.1, 1])

    with col_form:
        st.markdown("### 1. Select Client Case")
        case_options = list(all_cases.keys())
        selected_case_id = st.selectbox(
            "Benchmark Case",
            case_options,
            format_func=lambda cid: f"{cid}: {all_cases[cid].declared_name} ({all_cases[cid].client_type.value.upper()})",
        )
        case_data = all_cases[selected_case_id]

        st.markdown("### 2. Multi-Agent System Parameters")
        c1, c2 = st.columns(2)
        with c1:
            mode_choice = st.selectbox(
                "Messaging Architecture",
                [Mode.BLACKBOARD, Mode.HYBRID_P2P],
                format_func=lambda m: "Central Blackboard" if m == Mode.BLACKBOARD else "Hybrid Peer-to-Peer",
            )
            pattern_choice = st.selectbox(
                "Orchestration Pattern",
                [Pattern.SEQUENTIAL, Pattern.PARALLEL],
                format_func=lambda p: "Sequential Pipeline" if p == Pattern.SEQUENTIAL else "Parallel ThreadPool Dispatch",
            )
        with c2:
            persona_choice = st.selectbox(
                "Applicant Persona",
                [Persona.COOPERATIVE, Persona.IMPATIENT, Persona.ABUSIVE, Persona.FORGER, Persona.INJECTING],
                format_func=lambda p: f"{p.value.capitalize()} Persona",
            )
            reasoning_choice = st.selectbox(
                "Agent Reasoning Paradigm",
                [Reasoning.PLAIN, Reasoning.REACT],
                format_func=lambda r: "Plain Declarative" if r == Reasoning.PLAIN else "ReAct (Thought-Action-Observation)",
            )

        guardrails_enabled = st.checkbox("Enable Security Perimeter Guardrails (Toxicity & Injection)", value=True)

        if st.button("🚀 Run Multi-Agent Onboarding", type="primary", use_container_width=True):
            with st.spinner("Dispatching agents across Google ADK and CrewAI..."):
                active_run_id = f"ui_{case_data.case_id}_{mode_choice.value[:2]}_{pattern_choice.value[:3]}"

                # Inject persona if non-cooperative
                run_case_obj = case_data
                if persona_choice != Persona.COOPERATIVE:
                    run_case_obj, _ = inject_persona(case_data, persona_choice)

                config = RunConfig(
                    case_id=run_case_obj.case_id,
                    mode=mode_choice,
                    pattern=pattern_choice,
                    persona=persona_choice,
                    reasoning=reasoning_choice,
                    guardrails_enabled=guardrails_enabled,
                )

                orchestrator = Orchestrator()
                report = orchestrator.run_case(
                    case=run_case_obj,
                    board_client=client,
                    run_id=active_run_id,
                    config=config,
                )

                st.session_state.recent_reports[active_run_id] = report
                st.session_state.last_run_id = active_run_id

            st.success(f"Onboarding execution complete for `{active_run_id}`!")

    with col_summary:
        st.markdown("### Client Dossier Details")
        st.write(f"- **Declared Legal Name**: `{case_data.declared_name}`")
        st.write(f"- **Entity Type**: `{case_data.client_type.value.capitalize()}`")
        st.write(f"- **Jurisdiction**: `{case_data.declared_country}`")
        st.write(f"- **Declared Source of Funds**: `{case_data.declared_source_of_funds}`")
        st.write(f"- **Monthly Expected Volume**: `INR {case_data.expected_monthly_volume_inr:,.0f}`")
        st.write(f"- **Supporting Documents**: `{len(case_data.documents)} document(s)`")

        if case_data.documents:
            st.markdown("#### Document Previews")
            for doc_path in case_data.documents[:2]:
                p = Path(doc_path)
                if p.exists():
                    st.image(str(p), caption=p.name, width=320)

        # Show latest run outcome
        if st.session_state.last_run_id:
            latest_rep: OnboardingReport = st.session_state.recent_reports[st.session_state.last_run_id]
            st.markdown("---")
            st.markdown(f"### Latest Run Outcome (`{st.session_state.last_run_id}`)")

            d_color = "badge-approve"
            if latest_rep.decision.value == "approve_with_enhanced_monitoring":
                d_color = "badge-edd"
            elif latest_rep.decision.value == "escalate_to_human":
                d_color = "badge-escalate"

            st.markdown(
                f'<span class="{d_color}">DECISION: {latest_rep.decision.value.upper()}</span> &nbsp; '
                f'<strong>Tier:</strong> `{latest_rep.risk_tier.value.upper()}` &nbsp; '
                f'<strong>Score:</strong> `{latest_rep.risk_score:.0f}/100`',
                unsafe_allow_html=True,
            )
            st.markdown(f"**Rationale:** {latest_rep.decision_rationale}")
            st.write(f"- **Runtime:** `{latest_rep.total_runtime_s:.2f}s` | **Tokens:** `{sum(m.tokens for m in latest_rep.per_agent)}`")
            st.write(f"- **Planted Red Flags Detected:** `{len(latest_rep.red_flags)}`")


# =========================================================================
# View 2: Live Zoned Blackboard Inspector
# =========================================================================
elif nav == "🧠 Live Blackboard":
    st.markdown('<div class="main-header">Live Zoned Blackboard Inspector</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="sub-header">Audit shared state across Blackboard zones with cryptographic PII masking.</div>',
        unsafe_allow_html=True,
    )

    if not st.session_state.recent_reports:
        st.info("No active runs executed yet in this session. Head to **Client Application** and run a case first!")
    else:
        run_ids = list(st.session_state.recent_reports.keys())
        selected_run = st.selectbox("Active Blackboard Run", run_ids, index=len(run_ids) - 1)
        board = client.get_run(selected_run, agent_id="adk.orchestrator")

        st.markdown(f"**Active Phase:** `{board.phase.value.upper()}` | **Concurrency Version:** `v{board.version}`")

        tab_intake, tab_ver, tab_scr, tab_risk, tab_review, tab_sys = st.tabs(
            ["Intake Zone", "Verification Zone", "Screening Zone", "Risk Zone", "Review Zone", "System Zone"]
        )

        with tab_intake:
            st.markdown("#### Masked Profile (PII Safe)")
            st.json(board.intake.profile.model_dump())
            st.markdown("#### Extracted Documents")
            st.dataframe([d.model_dump() for d in board.intake.documents], use_container_width=True)

        with tab_ver:
            st.markdown("#### Identity Checks")
            st.dataframe([c.model_dump() for c in board.verification.checks], use_container_width=True)

        with tab_scr:
            st.markdown("#### Watchlist Hits (OFAC & PEP)")
            st.dataframe([h.model_dump() for h in board.screening.hits], use_container_width=True)
            st.markdown("#### Adverse Media Findings")
            st.dataframe([m.model_dump() for m in board.screening.media], use_container_width=True)
            st.markdown("#### Raised Red Flags")
            st.dataframe([f.model_dump() for f in board.screening.red_flags], use_container_width=True)

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
                        "human_override": f"Approved by {officer_name}: {officer_notes}",
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
                        "human_override": f"Rejected by {officer_name}: {officer_notes}",
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

    st.markdown("### Empirical Benchmark Plots")
    p_col1, p_col2 = st.columns(2)

    with p_col1:
        p1 = Path("results/plots/runtime_and_cost_boxplots.png")
        if p1.exists():
            st.image(str(p1), caption="Runtime & Cost: Sequential vs Parallel | Blackboard vs Hybrid P2P", use_container_width=True)

        p2 = Path("results/plots/tokens_per_run_by_mode.png")
        if p2.exists():
            st.image(str(p2), caption="Token Consumption Spread: Blackboard vs Hybrid P2P", use_container_width=True)

        p3 = Path("results/plots/heatmap_agent_phase_latency.png")
        if p3.exists():
            st.image(str(p3), caption="Agent x Phase Latency Heatmap (ms)", use_container_width=True)

    with p_col2:
        p4 = Path("results/plots/red_flag_recall_by_persona.png")
        if p4.exists():
            st.image(str(p4), caption="Red Flag Recall by Applicant Persona", use_container_width=True)

        p5 = Path("results/plots/injection_ablation_bar_chart.png")
        if p5.exists():
            st.image(str(p5), caption="Prompt Injection Attack Success Rate (Ablation)", use_container_width=True)

        p6 = Path("results/plots/heatmap_agent_errors_guardrails.png")
        if p6.exists():
            st.image(str(p6), caption="Errors & Guardrail Triggers Heatmap by Agent", use_container_width=True)


# =========================================================================
# View 5: OpenTelemetry Distributed Tracing & Audit Provenance Inspector
# =========================================================================
elif nav == "🔍 OpenTelemetry Provenance":
    st.markdown('<div class="main-header">OpenTelemetry Provenance & Distributed Traces</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="sub-header">Inspect 1-case-1-trace provenance, span hierarchies, and zero-PII audit guarantees.</div>',
        unsafe_allow_html=True,
    )

    if not st.session_state.recent_reports:
        st.info("Run an onboarding case from the **Client Application** tab to inspect its OpenTelemetry trace!")
    else:
        run_ids = list(st.session_state.recent_reports.keys())
        selected_run = st.selectbox("Inspect Trace for Run", run_ids, index=len(run_ids) - 1)
        prov = get_provenance_summary(selected_run)

        col_t1, col_t2 = st.columns(2)
        with col_t1:
            st.markdown("#### OpenTelemetry Trace Metadata")
            st.write(f"- **Case Run ID**: `{prov['run_id']}`")
            st.write(f"- **Deterministic 128-bit Trace ID**: `0x{prov['trace_id_hex']}`")
            st.write(f"- **Total Captured Spans**: `{prov['total_spans']}`")
            st.write(f"- **Provenance Audit Verified**: `{'✅ VERIFIED' if prov['provenance_verified'] else '❌ UNVERIFIED'}`")

        with col_t2:
            st.markdown("#### Trace Component Participation")
            st.write(f"- **Agents Traced**: `{', '.join(prov['agents_traced']) or 'None'}`")
            st.write(f"- **Tools Called**: `{', '.join(prov['tools_called']) or 'None'}`")
            st.write(f"- **Guardrail Checks**: `{', '.join(prov['guardrail_checks']) or 'None'}`")

        st.markdown("#### Span Hierarchy Trail")
        st.dataframe([{"Span Index": idx + 1, "Span Name": s_name} for idx, s_name in enumerate(prov["span_names"])], use_container_width=True)
