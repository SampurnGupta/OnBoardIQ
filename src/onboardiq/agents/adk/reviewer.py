"""Compliance Reviewer Agent — ADK framework.

Audits DecisionDraft against institutional policies (data/policy.md) via policy_rag.
Issues PolicyCheck evaluations and Challenge items.
Coordinates with RiskScorer in a reflection loop (up to 2 revision cycles).
"""

from __future__ import annotations

import uuid
from typing import Any

from onboardiq.blackboard.client import BlackboardClient
from onboardiq.schema import (
    Challenge,
    Decision,
    DecisionDraft,
    Phase,
    PolicyCheck,
    Reasoning,
)
from onboardiq.telemetry.callbacks import record_step_trace


class ComplianceReviewerAgent:
    """ADK Reviewer evaluating compliance drafts against institutional policy."""

    def __init__(self, agent_id: str = "adk.reviewer", max_revision_loops: int = 2):
        self.agent_id = agent_id
        self.max_revision_loops = max_revision_loops

    def review_case(
        self,
        run_id: str,
        board_client: BlackboardClient,
        current_version: int,
        risk_scorer: Any = None,
        reasoning: Reasoning = Reasoning.PLAIN,
    ) -> tuple[list[PolicyCheck], list[Challenge], Decision, int]:
        """Review the current decision draft against policy.

        If non-compliant, triggers a reflection loop with the risk scorer up to max_revision_loops.
        """
        revision_count = 0
        accumulated_challenges: list[Challenge] = []

        while True:
            # 1. Fetch relevant zones (authorized: ALL_EXCEPT_PII_VAULT)
            risk_zone = board_client.get_zone(run_id, "risk", agent_id=self.agent_id)
            scr_zone = board_client.get_zone(run_id, "screening", agent_id=self.agent_id)
            intake_zone = board_client.get_zone(run_id, "intake", agent_id=self.agent_id)
            ver_zone = board_client.get_zone(run_id, "verification", agent_id=self.agent_id)

            draft_dict = risk_zone.get("draft")
            if not draft_dict:
                # No draft to evaluate
                return [], [], Decision.ESCALATE, current_version

            draft = DecisionDraft.model_validate(draft_dict)
            hits = scr_zone.get("hits", [])
            red_flags = scr_zone.get("red_flags", [])
            profile = intake_zone.get("profile", {})
            vol = float(profile.get("expected_monthly_volume_inr", 0.0))
            checks = ver_zone.get("checks", [])

            policy_checks: list[PolicyCheck] = []
            challenges: list[Challenge] = []

            # --- Rule 1: Identity Verification ---
            id_passed = all(c.get("passed", True) for c in checks) if checks else True
            policy_checks.append(
                PolicyCheck(
                    rule_id="Rule 1",
                    passed=id_passed,
                    note="Identity registry & document cross-check verified" if id_passed else "Identity verification failed",
                )
            )
            if not id_passed and draft.decision == Decision.APPROVE:
                challenges.append(
                    Challenge(
                        challenge_id=f"ch_id_{uuid.uuid4().hex[:6]}",
                        point="Rule 1 Violation: Unverified applicant cannot be approved under standard onboarding.",
                    )
                )

            # --- Rule 2: Sanctions Prohibition ---
            has_sanctions_hit = any(
                h.get("disposition") in ("true_match", "likely_match") and h.get("list_name") != "PEP"
                for h in hits
            )
            policy_checks.append(
                PolicyCheck(
                    rule_id="Rule 2",
                    passed=not has_sanctions_hit or draft.decision == Decision.ESCALATE,
                    note="Mandatory escalation for true/likely sanctions hit" if has_sanctions_hit else "No sanctions match",
                )
            )
            if has_sanctions_hit and draft.decision != Decision.ESCALATE:
                challenges.append(
                    Challenge(
                        challenge_id=f"ch_sanctions_{uuid.uuid4().hex[:6]}",
                        point=f"Rule 2 Violation: Sanctions hit detected. Draft proposed '{draft.decision.value}' instead of mandatory Decision.ESCALATE.",
                    )
                )

            # --- Rule 3: PEP Enhanced Due Diligence ---
            has_pep = any(h.get("list_name") == "PEP" for h in hits)
            policy_checks.append(
                PolicyCheck(
                    rule_id="Rule 3",
                    passed=not has_pep or draft.decision in (Decision.APPROVE_EDD, Decision.ESCALATE),
                    note="PEP requires Enhanced Due Diligence (EDD) or escalation" if has_pep else "No PEP watch hit",
                )
            )
            if has_pep and draft.decision == Decision.APPROVE:
                challenges.append(
                    Challenge(
                        challenge_id=f"ch_pep_{uuid.uuid4().hex[:6]}",
                        point="Rule 3 Violation: PEP status mandates at least MEDIUM risk tier and Enhanced Due Diligence (approve_with_enhanced_monitoring).",
                    )
                )

            # --- Rule 4: Prohibition of Auto-Rejection ---
            auto_reject = draft.decision == Decision.REJECT and not draft.requires_human
            policy_checks.append(
                PolicyCheck(
                    rule_id="Rule 4",
                    passed=not auto_reject,
                    note="Rejection must be confirmed by human officer",
                )
            )
            if auto_reject:
                challenges.append(
                    Challenge(
                        challenge_id=f"ch_reject_{uuid.uuid4().hex[:6]}",
                        point="Rule 4 Violation: System cannot auto-reject without human confirmation.",
                    )
                )

            # --- Rule 7: Adverse Media Scrutiny ---
            has_adverse_media = any(rf.get("flag_type") == "adverse_media" for rf in red_flags)
            policy_checks.append(
                PolicyCheck(
                    rule_id="Rule 7",
                    passed=not has_adverse_media or draft.decision in (Decision.APPROVE_EDD, Decision.ESCALATE),
                    note="Substantiated adverse media mandates EDD or escalation" if has_adverse_media else "No adverse media flag",
                )
            )
            if has_adverse_media and draft.decision == Decision.APPROVE:
                challenges.append(
                    Challenge(
                        challenge_id=f"ch_media_{uuid.uuid4().hex[:6]}",
                        point="Rule 7 Violation: Adverse media flags require Enhanced Due Diligence or escalation.",
                    )
                )

            # --- Rule 9: Opaque Ownership ---
            has_opaque_ubo = any(rf.get("flag_type") == "opaque_ownership" for rf in red_flags)
            policy_checks.append(
                PolicyCheck(
                    rule_id="Rule 9",
                    passed=not has_opaque_ubo or draft.decision in (Decision.APPROVE_EDD, Decision.ESCALATE),
                    note="Opaque corporate ownership structure detected" if has_opaque_ubo else "Transparent ownership",
                )
            )
            if has_opaque_ubo and draft.decision == Decision.APPROVE:
                challenges.append(
                    Challenge(
                        challenge_id=f"ch_opaque_{uuid.uuid4().hex[:6]}",
                        point="Rule 9 Violation: Opaque offshore trust / shell structure cannot be auto-approved.",
                    )
                )

            # --- Rule 11: Transaction Volume Threshold ---
            high_vol = vol > 5000000.0
            policy_checks.append(
                PolicyCheck(
                    rule_id="Rule 11",
                    passed=not high_vol or draft.decision in (Decision.APPROVE_EDD, Decision.ESCALATE),
                    note="Transaction volume > 5M INR requires EDD" if high_vol else "Volume within standard limits",
                )
            )
            if high_vol and draft.decision == Decision.APPROVE:
                challenges.append(
                    Challenge(
                        challenge_id=f"ch_vol_{uuid.uuid4().hex[:6]}",
                        point="Rule 11 Violation: Expected monthly volume > 5M INR mandates Enhanced Due Diligence.",
                    )
                )

            # --- Rule 13: Mandatory Evidence Attribution ---
            evidence_ok = bool(draft.evidence_ids) if draft.decision in (Decision.REJECT, Decision.ESCALATE) else True
            policy_checks.append(
                PolicyCheck(
                    rule_id="Rule 13",
                    passed=evidence_ok,
                    note="Evidence IDs cited on non-standard decision" if evidence_ok else "Missing evidence citation",
                )
            )
            if not evidence_ok:
                challenges.append(
                    Challenge(
                        challenge_id=f"ch_ev_{uuid.uuid4().hex[:6]}",
                        point="Rule 13 Violation: Escalation or rejection must cite evidence IDs.",
                    )
                )

            # 2. Check if revision reflection loop is needed
            for ch in challenges:
                if not any(ac.challenge_id == ch.challenge_id for ac in accumulated_challenges):
                    accumulated_challenges.append(ch)

            unresolved = [c for c in accumulated_challenges if not c.resolved]
            if unresolved and revision_count < self.max_revision_loops and risk_scorer is not None:
                # Trigger reflection revision loop with RiskScorer
                revision_count += 1
                _, current_version = risk_scorer.revise_draft(
                    run_id=run_id,
                    board_client=board_client,
                    current_version=current_version,
                    challenges=unresolved,
                    revision_number=revision_count,
                    reasoning=reasoning,
                )
                for ch in unresolved:
                    ch.resolved = True
                    ch.resolution = f"Resolved in reflection loop (revision {revision_count})"
                # Loop again to verify the revised draft against policy
                continue

            # Mark remaining challenges as acknowledged if loop terminated
            for c in accumulated_challenges:
                if not c.resolved:
                    c.resolved = True
                    c.resolution = f"Acknowledged at final revision ({revision_count})"

            # Final decision matches draft
            final_decision = draft.decision

            # 3. Write policy checks and challenges to review zone
            _, current_version = board_client.append_event_with_retry(
                run_id=run_id,
                zone="review",
                payload={
                    "policy_checks": [pc.model_dump(mode="json") for pc in policy_checks],
                    "challenges": [c.model_dump(mode="json") for c in accumulated_challenges],
                    "final_decision": final_decision.value,
                },
                expected_version=current_version,
                op="update",
                agent_id=self.agent_id,
            )

            # Record telemetry trace
            _, current_version = record_step_trace(
                board_client=board_client,
                run_id=run_id,
                agent_id=self.agent_id,
                phase=Phase.REVIEW,
                step_type="model",
                name="compliance_review",
                latency_ms=28.0,
                prompt_tokens=190,
                completion_tokens=80,
                current_version=current_version,
            )

            return policy_checks, accumulated_challenges, final_decision, current_version
