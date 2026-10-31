"""ADK Security Gateway.

Splits incoming client application into:
1. PiiVault (restricted zone): raw identifying personal data (name, DOB, address, raw IDs)
2. MaskedProfile (intake zone): sanitized profile for non-privileged screening agents
3. GuardrailEvent: logs intake validation event
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from onboardiq.blackboard.client import BlackboardClient
from onboardiq.guardrails.input_guard import scan_text
from onboardiq.schema import (
    GuardrailEvent,
    LabelledCase,
    MaskedProfile,
    Phase,
    PiiVault,
)
from onboardiq.telemetry.callbacks import record_step_trace


def _compute_age_band(dob_str: str | None) -> str | None:
    """Compute approximate age band from YYYY-MM-DD string."""
    if not dob_str:
        return None
    try:
        birth_year = int(dob_str.split("-")[0])
        current_year = datetime.now(UTC).year
        age = current_year - birth_year
        if age < 20:
            return "under-20"
        elif age < 30:
            return "20-29"
        elif age < 40:
            return "30-39"
        elif age < 50:
            return "40-49"
        elif age < 60:
            return "50-59"
        else:
            return "60+"
    except (ValueError, IndexError):
        return None


def _mask_name(raw_name: str) -> str:
    """Mask full name to display format, e.g. 'Priya Sharma' -> 'Priya S.'."""
    parts = raw_name.strip().split()
    if len(parts) <= 1:
        return raw_name
    first = parts[0]
    last_initial = parts[-1][0].upper()
    return f"{first} {last_initial}."


class SecurityGateway:
    """Intake gateway agent responsible for PII separation and perimeter guardrails."""

    def __init__(self, agent_id: str = "adk.gateway"):
        self.agent_id = agent_id

    def process_application(
        self,
        case: LabelledCase,
        run_id: str,
        board_client: BlackboardClient,
        current_version: int = 0,
        guardrails_enabled: bool = True,
    ) -> tuple[MaskedProfile, PiiVault, int]:
        """Split raw application into PiiVault and MaskedProfile, updating the Blackboard."""
        # 1. Scan for input threats if guardrails enabled
        guardrail_event: GuardrailEvent
        if guardrails_enabled:
            corpus = f"{case.declared_name} {case.declared_address} {case.declared_source_of_funds}"
            _res, guardrail_event = scan_text(corpus, agent_id=self.agent_id, stage="input")
        else:
            guardrail_event = GuardrailEvent(
                event_id=str(uuid.uuid4()),
                stage="input",
                category="clean",
                action="allowed",
                agent_id=self.agent_id,
                score=0.0,
                detail="Guardrails disabled by RunConfig.",
            )

        # 2. Construct PiiVault
        pii = PiiVault(
            raw_name=case.declared_name,
            dob=case.declared_dob,
            address=case.declared_address,
            id_numbers={},
            raw_document_text={},
        )

        # 3. Construct MaskedProfile
        masked_profile = MaskedProfile(
            case_id=case.case_id,
            client_type=case.client_type,
            display_name=_mask_name(case.declared_name),
            country=case.declared_country,
            age_band=_compute_age_band(case.declared_dob),
            id_last4="****",
            source_of_funds=case.declared_source_of_funds,
            expected_monthly_volume_inr=case.expected_monthly_volume_inr,
        )

        # 4. Write PiiVault and MaskedProfile to Blackboard
        # Update intake zone
        board_client.append_event(
            run_id=run_id,
            zone="pii_vault",
            payload=pii.model_dump(),
            expected_version=current_version,
            op="replace",
            agent_id=self.agent_id,
        )
        current_version += 1

        board_client.append_event(
            run_id=run_id,
            zone="intake",
            payload={"profile": masked_profile.model_dump()},
            expected_version=current_version,
            op="update",
            agent_id=self.agent_id,
        )
        current_version += 1

        # Record guardrail event in system zone
        board_client.append_event(
            run_id=run_id,
            zone="system",
            payload={"field": "guardrail_events", "item": guardrail_event.model_dump(mode="json")},
            expected_version=current_version,
            op="append",
            agent_id=self.agent_id,
        )
        current_version += 1

        # Record telemetry trace
        _, current_version = record_step_trace(
            board_client=board_client,
            run_id=run_id,
            agent_id=self.agent_id,
            phase=Phase.INTAKE,
            step_type="model",
            name="intake_pii_isolation",
            latency_ms=18.5,
            prompt_tokens=180,
            completion_tokens=65,
            current_version=current_version,
        )

        return masked_profile, pii, current_version
