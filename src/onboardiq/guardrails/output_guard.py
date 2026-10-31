"""Output Guardrail for OnboardIQ.

Per docs/04_SECURITY.md:
1. Validates DecisionDraft compliance:
   - Automated rejections are forbidden (REJECT requires requires_human=True).
   - ESCALATE and REJECT require cited evidence_ids.
   - Rationale length <= 1200 characters.
2. Checks generated text/rationale/reports to ensure no raw unmasked PII leaks into output.
"""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import ValidationError

from onboardiq.guardrails.pii_guard import PAN_REGEX, PASSPORT_REGEX
from onboardiq.schema import Decision, DecisionDraft, GuardrailEvent, PiiVault


class OutputGuardResult:
    def __init__(
        self,
        is_valid: bool,
        action: str,
        category: str,
        error_message: str | None = None,
    ):
        self.is_valid = is_valid
        self.action = action
        self.category = category
        self.error_message = error_message


def validate_decision_draft(
    draft_data: dict[str, Any] | DecisionDraft,
    agent_id: str = "adk.orchestrator",
) -> tuple[OutputGuardResult, GuardrailEvent]:
    """Validate decision rules on DecisionDraft."""
    try:
        if isinstance(draft_data, dict):
            draft = DecisionDraft.model_validate(draft_data)
        else:
            draft = draft_data
    except ValidationError as exc:
        event = GuardrailEvent(
            event_id=str(uuid.uuid4()),
            stage="model_output",
            category="schema_violation",
            action="blocked",
            agent_id=agent_id,
            score=1.0,
            detail=f"Decision draft schema validation failed: {exc}",
        )
        return (
            OutputGuardResult(
                is_valid=False,
                action="blocked",
                category="schema_violation",
                error_message=str(exc),
            ),
            event,
        )

    # Decision rule 1: No auto-reject
    if draft.decision == Decision.REJECT and not draft.requires_human:
        msg = "Decision rules violation: REJECT requires requires_human=True (no automated rejections)."
        event = GuardrailEvent(
            event_id=str(uuid.uuid4()),
            stage="model_output",
            category="schema_violation",
            action="blocked",
            agent_id=agent_id,
            score=1.0,
            detail=msg,
        )
        return OutputGuardResult(is_valid=False, action="blocked", category="auto_reject_forbidden", error_message=msg), event

    # Decision rule 2: Escalate or reject must have evidence
    if draft.decision in (Decision.ESCALATE, Decision.REJECT) and not draft.evidence_ids:
        msg = f"Decision rules violation: {draft.decision.value} requires non-empty evidence_ids."
        event = GuardrailEvent(
            event_id=str(uuid.uuid4()),
            stage="model_output",
            category="schema_violation",
            action="blocked",
            agent_id=agent_id,
            score=1.0,
            detail=msg,
        )
        return OutputGuardResult(is_valid=False, action="blocked", category="missing_evidence", error_message=msg), event

    clean_event = GuardrailEvent(
        event_id=str(uuid.uuid4()),
        stage="model_output",
        category="clean",
        action="allowed",
        agent_id=agent_id,
        score=0.0,
        detail="Decision draft validated successfully.",
    )
    return OutputGuardResult(is_valid=True, action="allowed", category="clean"), clean_event


def scan_output_text(
    text: str,
    pii_vault: PiiVault | dict[str, Any] | None = None,
    agent_id: str = "adk.orchestrator",
) -> tuple[OutputGuardResult, GuardrailEvent]:
    """Scan output text to ensure raw vault PII is not leaked."""
    leaks = []
    if PAN_REGEX.search(text):
        leaks.append("PAN_regex")
    if PASSPORT_REGEX.search(text):
        leaks.append("Passport_regex")

    if pii_vault:
        v = pii_vault.model_dump() if isinstance(pii_vault, PiiVault) else pii_vault
        raw_id = v.get("raw_national_id")
        if raw_id and str(raw_id) in text:
            leaks.append("raw_national_id")
        raw_addr = v.get("address") or v.get("raw_address")
        if raw_addr and len(str(raw_addr)) > 6 and str(raw_addr).lower() in text.lower():
            leaks.append("raw_address")

    if leaks:
        event = GuardrailEvent(
            event_id=str(uuid.uuid4()),
            stage="model_output",
            category="pii_leak",
            action="blocked",
            agent_id=agent_id,
            score=1.0,
            detail=f"Output text leaked sensitive PII: {', '.join(leaks)}",
        )
        return (
            OutputGuardResult(
                is_valid=False,
                action="blocked",
                category="pii_leak",
                error_message=f"Leaked sensitive fields: {', '.join(leaks)}",
            ),
            event,
        )

    clean_event = GuardrailEvent(
        event_id=str(uuid.uuid4()),
        stage="model_output",
        category="clean",
        action="allowed",
        agent_id=agent_id,
        score=0.0,
        detail="Output text clean of raw PII.",
    )
    return OutputGuardResult(is_valid=True, action="allowed", category="clean"), clean_event
