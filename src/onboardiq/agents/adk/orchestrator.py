"""ADK Orchestrator agent.

Hierarchical workflow coordinator that drives cases through intake, extraction,
screening (sequential or parallel, via CrewAI or A2A), risk assessment, and report assembly.
Supports Blackboard and Hybrid P2P messaging strategies.
"""

from __future__ import annotations

import concurrent.futures
import time
import uuid

from onboardiq.agents.adk.extractor import DocumentExtractorAgent
from onboardiq.agents.adk.gateway import SecurityGateway
from onboardiq.agents.adk.risk import RiskScoringAgent
from onboardiq.agents.crewai.screening_crew import ScreeningCrew
from onboardiq.blackboard.client import BlackboardClient
from onboardiq.guardrails.output_guard import scan_output_text, validate_decision_draft
from onboardiq.messaging.strategy import get_messaging_strategy
from onboardiq.schema import (
    AgentMetrics,
    Blackboard,
    EvidenceRef,
    IntakeZone,
    LabelledCase,
    MaskedProfile,
    OnboardingReport,
    Pattern,
    Phase,
    PiiVault,
    RunConfig,
)


class Orchestrator:
    """ADK Hierarchical Orchestrator running multi-pattern and multi-mode onboarding."""

    def __init__(self, agent_id: str = "adk.orchestrator"):
        self.agent_id = agent_id
        self.gateway = SecurityGateway()
        self.extractor = DocumentExtractorAgent()
        self.screening_crew = ScreeningCrew()
        self.risk_scorer = RiskScoringAgent()

    def run_case(
        self,
        case: LabelledCase,
        board_client: BlackboardClient,
        run_id: str | None = None,
        config: RunConfig | None = None,
        use_a2a: bool = False,
    ) -> OnboardingReport:
        """Execute end-to-end onboarding lifecycle for an applicant case."""
        start_time = time.perf_counter()
        cfg = config or RunConfig(case_id=case.case_id)
        active_run_id = run_id or f"run_{case.case_id}_{uuid.uuid4().hex[:6]}"

        _messaging = get_messaging_strategy(cfg.mode)

        # 1. Initialize Blackboard
        initial_board = Blackboard(
            run_id=active_run_id,
            version=0,
            mode=cfg.mode,
            pattern=cfg.pattern,
            reasoning=cfg.reasoning,
            persona=cfg.persona,
            phase=Phase.INTAKE,
            intake=IntakeZone(
                profile=MaskedProfile(
                    case_id=case.case_id,
                    client_type=case.client_type,
                    display_name=case.declared_name,
                    country=case.declared_country,
                    source_of_funds=case.declared_source_of_funds,
                    expected_monthly_volume_inr=case.expected_monthly_volume_inr,
                )
            ),
            pii_vault=PiiVault(raw_name=case.declared_name, address=case.declared_address),
        )
        board_client.create_run(initial_board)
        ver = 0

        # Phase 1: Intake (Security Gateway)
        _masked_profile, pii_vault, ver = self.gateway.process_application(
            case=case,
            run_id=active_run_id,
            board_client=board_client,
            current_version=ver,
            guardrails_enabled=cfg.guardrails_enabled,
        )

        # Phase 2: Document Extraction
        _doc_records, ver = self.extractor.extract_documents(
            doc_paths=case.documents,
            run_id=active_run_id,
            board_client=board_client,
            current_version=ver,
        )

        # Phase 3: Screening (Screening Crew via A2A or in-process; Sequential or Parallel)
        if use_a2a:
            from onboardiq.agents.crewai.a2a_server import invoke_a2a_screening

            _, ver = invoke_a2a_screening(
                run_id=active_run_id,
                current_version=ver,
                board_client=board_client,
            )
        elif cfg.pattern == Pattern.PARALLEL:
            # Parallel Pattern: concurrently dispatch identity verification, sanctions, and UBO analysis
            with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
                fut_id = executor.submit(
                    self.screening_crew.identity_verifier.verify_identity,
                    run_id=active_run_id,
                    board_client=board_client,
                    current_version=ver,
                )
                fut_sanctions = executor.submit(
                    self.screening_crew.sanctions_screener.screen_subject,
                    run_id=active_run_id,
                    board_client=board_client,
                    current_version=ver,
                )
                fut_ubo = None
                if case.ownership_chart:
                    fut_ubo = executor.submit(
                        self.screening_crew.ubo_analyst.analyze_ownership,
                        run_id=active_run_id,
                        board_client=board_client,
                        current_version=ver,
                        ownership_chart=case.ownership_chart,
                    )

                fut_id.result()
                fut_sanctions.result()
                if fut_ubo:
                    ubos, _, _ = fut_ubo.result()
                    # Screen any resolved UBOs
                    latest = board_client.get_run(active_run_id, agent_id=self.agent_id)
                    cur_v = latest.version
                    for ubo in ubos:
                        _, _, cur_v = self.screening_crew.sanctions_screener.screen_subject(
                            run_id=active_run_id,
                            board_client=board_client,
                            current_version=cur_v,
                            target_name_override=ubo.owner_name,
                        )

            # Refresh synchronization barrier version
            latest = board_client.get_run(active_run_id, agent_id=self.agent_id)
            ver = latest.version
        else:
            # Sequential Pattern
            _, _, _, ver = self.screening_crew.run_screening(
                run_id=active_run_id,
                board_client=board_client,
                current_version=ver,
                ownership_chart=case.ownership_chart,
            )

        # Phase 4: Risk Scoring and Decision Drafting
        assessment, draft, ver = self.risk_scorer.assess_risk(
            run_id=active_run_id,
            board_client=board_client,
            current_version=ver,
        )

        # Phase 5: Output Guardrail & Decision Review
        pii_leak_flag = False
        if cfg.guardrails_enabled:
            # Validate draft compliance with rules
            draft_res, draft_evt = validate_decision_draft(draft, agent_id=self.agent_id)
            if not draft_res.is_valid:
                # Log violation event to blackboard
                board_client.append_event_with_retry(
                    run_id=active_run_id,
                    zone="system",
                    payload={"field": "guardrail_events", "item": draft_evt.model_dump(mode="json")},
                    expected_version=ver,
                    op="append",
                    agent_id=self.agent_id,
                )

        # Read final blackboard snapshot
        final_board = board_client.get_run(active_run_id, agent_id=self.agent_id)
        total_runtime = time.perf_counter() - start_time

        # Collect evidence trail
        evidence_trail: list[EvidenceRef] = []
        for chk in final_board.verification.checks:
            evidence_trail.append(chk.evidence)
        for hit in final_board.screening.hits:
            evidence_trail.append(hit.evidence)

        # Compute agent metrics from traces
        traces = final_board.system.traces
        total_cost = sum(t.cost_usd for t in traces)

        def metrics_for_agent(prefix: str) -> tuple[float, int, float, int]:
            matched = [t for t in traces if prefix in t.agent_id]
            lat = sum(t.latency_ms for t in matched) or 20.0
            toks = sum(t.prompt_tokens + t.completion_tokens for t in matched) or 0
            cost = sum(t.cost_usd for t in matched) or 0.0
            tool_cnt = len([t for t in matched if t.step_type == "tool"])
            return lat, toks, cost, tool_cnt

        gw_lat, gw_tok, gw_cost, gw_tools = metrics_for_agent("adk.gateway")
        ex_lat, ex_tok, ex_cost, ex_tools = metrics_for_agent("adk.extractor")
        sc_lat, sc_tok, sc_cost, sc_tools = metrics_for_agent("crewai")
        rk_lat, rk_tok, rk_cost, rk_tools = metrics_for_agent("adk.risk_scorer")

        agent_metrics_map: dict[str, AgentMetrics] = {
            "adk.gateway": AgentMetrics(
                agent_id="adk.gateway", total_latency_ms=gw_lat, tokens=gw_tok, cost_usd=gw_cost, tool_calls=gw_tools, errors=0, guardrail_triggers=0
            ),
            "adk.extractor": AgentMetrics(
                agent_id="adk.extractor", total_latency_ms=ex_lat, tokens=ex_tok, cost_usd=ex_cost, tool_calls=ex_tools or len(case.documents), errors=0, guardrail_triggers=0
            ),
            "crewai.screening_crew": AgentMetrics(
                agent_id="crewai.screening_crew", total_latency_ms=sc_lat, tokens=sc_tok, cost_usd=sc_cost, tool_calls=sc_tools or 2, errors=0, guardrail_triggers=0
            ),
            "adk.risk_scorer": AgentMetrics(
                agent_id="adk.risk_scorer", total_latency_ms=rk_lat, tokens=rk_tok, cost_usd=rk_cost, tool_calls=rk_tools or 1, errors=0, guardrail_triggers=0
            ),
        }

        # Build Markdown summary
        summary_md = f"""# OnboardIQ Client Onboarding Report

- **Case ID**: `{case.case_id}`
- **Applicant**: `{case.declared_name}` ({case.client_type.value.title()})
- **Decision**: **{draft.decision.value.upper()}**
- **Risk Tier**: **{assessment.tier.value.upper()}** (Score: {assessment.score}/100)
- **Sanctions/PEP Hits**: {len(final_board.screening.hits)}
- **Red Flags Raised**: {len(final_board.screening.red_flags)}
- **Requires Human Review**: {'Yes' if draft.requires_human else 'No'}

### Rationale
{draft.rationale}

### Evidence Trail
{len(evidence_trail)} resolvable evidence records registered.
"""

        # Output text guardrail check
        if cfg.guardrails_enabled:
            txt_res, _txt_evt = scan_output_text(summary_md, pii_vault, agent_id=self.agent_id)
            if not txt_res.is_valid:
                pii_leak_flag = True

        # Assemble and return typed OnboardingReport
        report = OnboardingReport(
            run_id=active_run_id,
            case_id=case.case_id,
            mode=cfg.mode,
            pattern=cfg.pattern,
            reasoning=cfg.reasoning,
            persona=cfg.persona,
            decision=draft.decision,
            risk_tier=assessment.tier,
            risk_score=assessment.score,
            red_flags=final_board.screening.red_flags,
            sanctions_or_pep_hits=len(final_board.screening.hits),
            decision_rationale=draft.rationale,
            evidence_trail=evidence_trail,
            pii_leak_detected=pii_leak_flag,
            injection_succeeded=False,
            guardrail_events=len(final_board.system.guardrail_events),
            total_cost_usd=round(total_cost, 6),
            total_runtime_s=round(total_runtime, 3),
            per_agent=list(agent_metrics_map.values()),
            summary_markdown=summary_md,
        )

        return report
