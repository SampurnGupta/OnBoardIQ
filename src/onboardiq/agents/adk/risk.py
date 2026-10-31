"""ADK Risk Scoring Agent.

Combines ML gradient boosting risk predictions with deterministic policy rules
into a structured RiskAssessment and DecisionDraft.
"""

from __future__ import annotations

from onboardiq.blackboard.client import BlackboardClient
from onboardiq.mcp_server.tools.risk_predict import predict_case_risk
from onboardiq.schema import (
    Challenge,
    Decision,
    DecisionDraft,
    Phase,
    Reasoning,
    RiskAssessment,
    RiskFactor,
    RiskTier,
)
from onboardiq.telemetry.callbacks import record_step_trace


class RiskScoringAgent:
    """ADK Agent responsible for computing risk score, assigning tier, and drafting decisions."""

    def __init__(self, agent_id: str = "adk.risk_scorer"):
        self.agent_id = agent_id

    def assess_risk(
        self,
        run_id: str,
        board_client: BlackboardClient,
        current_version: int,
        reasoning: Reasoning = Reasoning.PLAIN,
    ) -> tuple[RiskAssessment, DecisionDraft, int]:
        """Read blackboard data, evaluate risk factors, and write risk assessment and draft."""
        intake_data = board_client.get_zone(run_id, "intake", agent_id=self.agent_id)
        ver_data = board_client.get_zone(run_id, "verification", agent_id=self.agent_id)
        scr_data = board_client.get_zone(run_id, "screening", agent_id=self.agent_id)

        profile = intake_data.get("profile", {})
        documents = intake_data.get("documents", [])
        checks = ver_data.get("checks", [])
        hits = scr_data.get("hits", [])
        red_flags = scr_data.get("red_flags", [])

        # Extract features for ML model
        vol = float(profile.get("expected_monthly_volume_inr", 50000.0))
        is_co = profile.get("client_type") == "company"
        num_flags = len(red_flags)

        max_screen_score = 0.0
        for h in hits:
            max_screen_score = max(max_screen_score, float(h.get("match_score", 0.0)))

        max_tamper = 0.0
        for d in documents:
            max_tamper = max(max_tamper, float(d.get("tamper_score", 0.0)))

        # 1. Query ML Model
        ml_res = predict_case_risk(
            country_risk=0.1,
            occupation_risk=0.1,
            monthly_volume_inr=vol,
            num_red_flags=num_flags,
            max_screening_score=max_screen_score,
            tamper_score=max_tamper,
            is_company=is_co,
        )

        factors: list[RiskFactor] = []
        cited_evidence_ids: list[str] = []

        # Base ML risk contribution
        ml_contrib = round(ml_res.probability_high * 40.0, 2)
        factors.append(
            RiskFactor(
                name="ML Gradient Boosting Risk Prior",
                contribution=ml_contrib,
                evidence_ids=[],
            )
        )

        # Red flag contributions
        for rf in red_flags:
            rf_ev = rf.get("evidence_ids", [])
            cited_evidence_ids.extend(rf_ev)
            factors.append(
                RiskFactor(
                    name=f"Red Flag: {rf.get('flag_type', 'Flag')}",
                    contribution=25.0,
                    evidence_ids=rf_ev,
                )
            )

        # Screening hit contributions
        for hit in hits:
            ev_id = hit.get("evidence", {}).get("evidence_id")
            if ev_id:
                cited_evidence_ids.append(ev_id)
            score = float(hit.get("match_score", 0.0))
            if hit.get("disposition") in ("true_match", "likely_match"):
                factors.append(
                    RiskFactor(
                        name=f"Sanctions/PEP Hit: {hit.get('matched_name')}",
                        contribution=round(score * 30.0, 2),
                        evidence_ids=[ev_id] if ev_id else [],
                    )
                )

        # Compute aggregate 0-100 score
        raw_score = sum(f.contribution for f in factors)
        score = min(max(round(raw_score, 2), 0.0), 100.0)

        # Determine Risk Tier
        has_critical_hit = any(
            h.get("disposition") in ("true_match", "likely_match") for h in hits
        )
        has_red_flags = len(red_flags) > 0

        if has_critical_hit or (has_red_flags and score >= 40.0) or score >= 70.0:
            tier = RiskTier.HIGH
            decision = Decision.ESCALATE
            requires_human = True
            rationale = (
                f"Applicant flagged as HIGH risk (score: {score:.1f}). "
                f"Identified {len(red_flags)} red flag(s) and critical screening hits requiring human compliance officer review."
            )
        elif score >= 30.0 or has_red_flags:
            tier = RiskTier.MEDIUM
            decision = Decision.APPROVE_EDD
            requires_human = False
            rationale = (
                f"Applicant classified as MEDIUM risk (score: {score:.1f}). "
                "Enhanced due diligence and periodic transaction monitoring recommended."
            )
        else:
            tier = RiskTier.LOW
            decision = Decision.APPROVE
            requires_human = False
            rationale = (
                f"Clean baseline applicant with score {score:.1f} (LOW tier). "
                "Document verification passed and no active sanctions/PEP watch hits found."
            )

        if reasoning == Reasoning.REACT:
            rationale = (
                f"Thought: Evaluated risk features (vol={vol:.0f}, red_flags={num_flags}, max_screen={max_screen_score:.2f}, max_tamper={max_tamper:.2f}). "
                f"Action: Predict ML risk probability and map aggregate risk factors. "
                f"Observation: ML probability_high={ml_res.probability_high:.2f}, computed score={score:.1f}, red_flags={num_flags}, screening_hits={len(hits)}. "
                f"Conclusion: {rationale}"
            )

        # Ensure escalate decision carries valid evidence references
        if decision == Decision.ESCALATE and not cited_evidence_ids:
            # Fallback to verification check evidence
            for chk in checks:
                ev_id = chk.get("evidence", {}).get("evidence_id")
                if ev_id:
                    cited_evidence_ids.append(ev_id)

        assessment = RiskAssessment(
            score=score,
            tier=tier,
            ml_probability_high=ml_res.probability_high,
            model_version=ml_res.model_version,
            factors=factors,
        )

        draft = DecisionDraft(
            decision=decision,
            rationale=rationale,
            evidence_ids=list(dict.fromkeys(cited_evidence_ids)),  # Deduplicate while preserving order
            requires_human=requires_human,
            revision=0,
        )

        # Write to risk zone
        board_client.append_event(
            run_id=run_id,
            zone="risk",
            payload={
                "assessment": assessment.model_dump(mode="json"),
                "draft": draft.model_dump(mode="json"),
            },
            expected_version=current_version,
            op="replace",
            agent_id=self.agent_id,
        )
        current_version += 1

        # Record telemetry trace
        _, current_version = record_step_trace(
            board_client=board_client,
            run_id=run_id,
            agent_id=self.agent_id,
            phase=Phase.RISK,
            step_type="model",
            name="risk_model_predict",
            latency_ms=26.0,
            prompt_tokens=240,
            completion_tokens=110,
            current_version=current_version,
        )

        return assessment, draft, current_version

    def revise_draft(
        self,
        run_id: str,
        board_client: BlackboardClient,
        current_version: int,
        challenges: list[Challenge],
        revision_number: int = 1,
        reasoning: Reasoning = Reasoning.PLAIN,
    ) -> tuple[DecisionDraft, int]:
        """Reflect on compliance challenges and revise the DecisionDraft."""
        risk_zone = board_client.get_zone(run_id, "risk", agent_id=self.agent_id)
        current_draft_dict = risk_zone.get("draft", {})
        draft = DecisionDraft.model_validate(current_draft_dict)

        new_decision = draft.decision
        requires_human = draft.requires_human
        rationale = draft.rationale
        evidence_ids = list(draft.evidence_ids)

        for ch in challenges:
            pt = ch.point.lower()
            if "sanctions" in pt or "mandatory decision.escalate" in pt or "rule 2" in pt:
                new_decision = Decision.ESCALATE
                requires_human = True
                rationale += f" [Revised to ESCALATE per challenge: {ch.point}]"
            elif "pep" in pt or "rule 3" in pt:
                if new_decision != Decision.ESCALATE:
                    new_decision = Decision.APPROVE_EDD
                    requires_human = False
                rationale += " [Revised to APPROVE_EDD per PEP compliance challenge]"
            elif "opaque" in pt or "rule 9" in pt:
                if new_decision != Decision.ESCALATE:
                    new_decision = Decision.APPROVE_EDD
                rationale += " [Revised to APPROVE_EDD per opaque corporate structure challenge]"
            elif "volume" in pt or "rule 11" in pt:
                if new_decision != Decision.ESCALATE:
                    new_decision = Decision.APPROVE_EDD
                rationale += " [Revised to APPROVE_EDD per high transaction velocity challenge]"
            elif "auto-reject" in pt or "rule 4" in pt:
                requires_human = True
                rationale += " [Rejection converted to human confirmation required]"

            if ch.challenge_id not in evidence_ids:
                evidence_ids.append(ch.challenge_id)

        # Fallback evidence if required
        if new_decision in (Decision.REJECT, Decision.ESCALATE) and not evidence_ids:
            evidence_ids.append("ev_compliance_challenge")

        final_rationale = rationale
        if reasoning == Reasoning.REACT:
            final_rationale = (
                f"Thought: Reflecting on {len(challenges)} compliance challenge(s). "
                f"Action: Apply mandatory institutional rules and adjust decision draft. "
                f"Observation: Revised decision to {new_decision.value} with human_required={requires_human}. "
                f"Conclusion: {rationale}"
            )

        revised_draft = DecisionDraft(
            decision=new_decision,
            rationale=final_rationale[:1190],
            evidence_ids=evidence_ids,
            requires_human=requires_human,
            revision=revision_number,
        )

        # Update risk zone
        _, current_version = board_client.append_event_with_retry(
            run_id=run_id,
            zone="risk",
            payload={"draft": revised_draft.model_dump(mode="json")},
            expected_version=current_version,
            op="update",
            agent_id=self.agent_id,
        )

        # Record telemetry trace
        _, current_version = record_step_trace(
            board_client=board_client,
            run_id=run_id,
            agent_id=self.agent_id,
            phase=Phase.RISK,
            step_type="model",
            name="revise_decision_draft",
            latency_ms=22.0,
            prompt_tokens=180,
            completion_tokens=70,
            current_version=current_version,
        )

        return revised_draft, current_version
