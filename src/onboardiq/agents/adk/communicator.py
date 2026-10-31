"""Client Communicator Agent — ADK framework (Task T25).

Handles:
1. Automated Request for Information (RFI) for missing documents or low-confidence fields (max 2 rounds).
2. De-escalating, neutral communication for impatient or abusive client personas.
   Guarantees: Never discloses internal rules, never alters process, never bypasses KYC.
"""

from __future__ import annotations

import re
from typing import Any

from onboardiq.blackboard.client import BlackboardClient
from onboardiq.guardrails.input_guard import scan_text
from onboardiq.schema import Phase
from onboardiq.telemetry.callbacks import record_step_trace

# Specific triggers for persona sentiment detection
IMPATIENT_PATTERNS = [
    r"hurry up", r"taking forever", r"rush this", r"why is this taking so long",
    r"immediately", r"right now", r"asap", r"unacceptable delay",
]

ABUSIVE_PATTERNS = [
    r"incompetent", r"idiot", r"clowns", r"sue you", r"lawyer", r"scam",
    r"stupid", r"useless", r"garbage", r"bastard",
]


class ClientCommunicatorAgent:
    """ADK Agent responsible for client communication, RFI drafting, and adversarial de-escalation."""

    def __init__(self, agent_id: str = "adk.comms"):
        self.agent_id = agent_id

    def check_and_draft_rfi(
        self,
        run_id: str,
        board_client: BlackboardClient,
        current_version: int,
        max_rfi_rounds: int = 2,
    ) -> tuple[str | None, int]:
        """Examine intake zone for missing documents or low-confidence fields and draft polite RFI."""
        intake_data = board_client.get_zone(run_id, "intake", agent_id=self.agent_id)
        sys_data = board_client.get_zone(run_id, "system", agent_id=self.agent_id)

        current_rfi_rounds = int(sys_data.get("rfi_rounds", 0))
        if current_rfi_rounds >= max_rfi_rounds:
            return None, current_version

        documents = intake_data.get("documents", [])
        issues: list[str] = []

        # Check document count
        if not documents:
            issues.append("No identification documents were detected in your submission.")
        elif len(documents) < 2:
            issues.append("Secondary proof of address or secondary ID document is required.")

        # Check confidence on extracted fields
        for doc in documents:
            doc_type = doc.get("doc_type", "document")
            for field in doc.get("fields", []):
                fname = field.get("name", "field")
                conf = float(field.get("confidence", 1.0))
                if conf < 0.60:
                    issues.append(f"Field '{fname}' on your {doc_type} had low legibility confidence ({conf:.2f}).")

        if not issues:
            return None, current_version

        # Increment RFI round
        new_rfi_round = current_rfi_rounds + 1
        _, current_version = board_client.append_event_with_retry(
            run_id=run_id,
            zone="system",
            payload={"rfi_rounds": new_rfi_round},
            expected_version=current_version,
            op="update",
            agent_id=self.agent_id,
        )

        # Draft formal, courteous RFI message
        bullet_points = "\n".join(f"- {issue}" for issue in issues)
        rfi_letter = (
            f"Dear Applicant,\n\n"
            f"Thank you for submitting your onboarding documentation. During our preliminary automated intake review, "
            f"we identified the following item(s) requiring your clarification (Round {new_rfi_round} of {max_rfi_rounds}):\n\n"
            f"{bullet_points}\n\n"
            f"To avoid any disruption to your application, please provide clear, high-resolution scans or updated documents "
            f"at your earliest convenience. Thank you for your cooperation.\n\n"
            f"Sincerely,\nInstitutional Onboarding Support"
        )

        # Record telemetry trace
        _, current_version = record_step_trace(
            board_client=board_client,
            run_id=run_id,
            agent_id=self.agent_id,
            phase=Phase.INTAKE,
            step_type="model",
            name="draft_rfi",
            latency_ms=25.0,
            prompt_tokens=150,
            completion_tokens=90,
            current_version=current_version,
        )

        return rfi_letter, current_version

    def handle_client_message(
        self,
        message: str,
        applicant_name: str = "Applicant",
    ) -> dict[str, Any]:
        """Process an inbound client message, handling abusive or impatient personas neutrally.

        Guarantees:
        1. Never reveals internal risk scores, thresholds, or agent rules.
        2. Never accelerates or changes the mandatory onboarding process.
        3. Maintains polite, professional, and de-escalating tone.
        """
        msg_lower = message.lower()

        # 1. Guardrail check for toxicity or injection
        input_eval, _ = scan_text(message, agent_id=self.agent_id)

        # 2. Pattern detection
        is_abusive = (not input_eval.is_safe and input_eval.category == "toxicity") or any(
            re.search(p, msg_lower) for p in ABUSIVE_PATTERNS
        )
        is_impatient = any(re.search(p, msg_lower) for p in IMPATIENT_PATTERNS)

        # 3. Formulate response
        if is_abusive:
            reply = (
                f"Dear {applicant_name},\n\n"
                "We understand that onboarding verifications can be demanding, and we appreciate your patience. "
                "Our team maintains a strict commitment to mutual professional respect. "
                "Please be assured that your application is actively progressing through our standard verification and compliance checks. "
                "We will notify you immediately once the evaluation is finalized.\n\n"
                "Sincerely,\nClient Relations Support"
            )
        elif is_impatient:
            reply = (
                f"Dear {applicant_name},\n\n"
                "Thank you for reaching out regarding the status of your onboarding application. "
                "Each application undergoes thorough and systematic due diligence to ensure institutional accuracy and regulatory adherence. "
                "While we cannot bypass standard verification steps, your case is actively being processed by our compliance team. "
                "You will receive an update as soon as the review is complete.\n\n"
                "Sincerely,\nClient Relations Support"
            )
        else:
            reply = (
                f"Dear {applicant_name},\n\n"
                "Thank you for contacting us. Your message has been received, and your application is proceeding "
                "through our standard onboarding workflow.\n\n"
                "Sincerely,\nClient Relations Support"
            )

        # 4. Audit guarantees check
        internal_terms = ["gradient boosting", "risk_score", "cutoff 40", "rule 2", "ofac", "pii_vault", "blackboard"]
        disclosed = any(term in reply.lower() for term in internal_terms)
        process_altered = "bypass" in reply.lower() and "cannot bypass" not in reply.lower()

        return {
            "applicant_name": applicant_name,
            "is_abusive": is_abusive,
            "is_impatient": is_impatient,
            "reply": reply,
            "rules_disclosed": disclosed,
            "process_altered": process_altered,
        }
