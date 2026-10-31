"""PII Guardrail for outbound tool queries and agent communication.

Per docs/04_SECURITY.md Section 2 & 6:
- Outbound queries to external tools (sanctions, news, registry) must not contain
  unmasked identity numbers (PAN, Passport), DOB, or raw residential addresses.
- Blocks leaked PII and records GuardrailEvent(stage="tool_input", category="pii_leak", action="blocked").
"""

from __future__ import annotations

import re
import uuid
from typing import Any

from onboardiq.schema import GuardrailEvent, PiiVault

# Regex patterns for high-sensitivity PII identifiers
PAN_REGEX = re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b", re.IGNORECASE)
PASSPORT_REGEX = re.compile(r"\b[A-Z][0-9]{7,8}\b", re.IGNORECASE)
DOB_REGEX = re.compile(r"\b(19\d\d|20\d\d)-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])\b")
EMAIL_REGEX = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")
PHONE_REGEX = re.compile(r"\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b")

# Tools that are allowed to handle internal PII vs external outbound tools
INTERNAL_ALLOWED_TOOLS = {"blackboard_read", "blackboard_write", "doc_ocr"}


class PiiGuardResult:
    def __init__(
        self,
        is_safe: bool,
        leaked_fields: list[str],
        detail: str,
        action: str = "allowed",
    ):
        self.is_safe = is_safe
        self.leaked_fields = leaked_fields
        self.detail = detail
        self.action = action


def scan_tool_arguments(
    tool_name: str,
    args: dict[str, Any],
    pii_vault: PiiVault | dict[str, Any] | None = None,
    agent_id: str = "agent",
) -> tuple[PiiGuardResult, GuardrailEvent]:
    """Scan outbound tool arguments for unmasked PII.

    Returns (PiiGuardResult, GuardrailEvent).
    """
    if tool_name in INTERNAL_ALLOWED_TOOLS:
        event = GuardrailEvent(
            event_id=str(uuid.uuid4()),
            stage="tool_input",
            category="clean",
            action="allowed",
            agent_id=agent_id,
            score=0.0,
            detail=f"Internal tool '{tool_name}' allowed.",
        )
        return PiiGuardResult(is_safe=True, leaked_fields=[], detail="Internal tool", action="allowed"), event

    # Convert all string arguments to a combined corpus for scanning
    def extract_strings(obj: Any) -> list[str]:
        items: list[str] = []
        if isinstance(obj, str):
            items.append(obj)
        elif isinstance(obj, dict):
            for v in obj.values():
                items.extend(extract_strings(v))
        elif isinstance(obj, (list, tuple, set)):
            for v in obj:
                items.extend(extract_strings(v))
        return items

    string_values = extract_strings(args)
    full_text = " ".join(string_values)

    leaks: list[str] = []

    # 1. Check regex patterns
    if PAN_REGEX.search(full_text):
        leaks.append("PAN_number")
    if PASSPORT_REGEX.search(full_text):
        leaks.append("Passport_number")

    # 2. Check vault values directly if provided
    if pii_vault:
        vault_dict = pii_vault.model_dump() if isinstance(pii_vault, PiiVault) else pii_vault

        # Check raw_national_id or id_numbers values
        id_numbers = vault_dict.get("id_numbers", {})
        if isinstance(id_numbers, dict):
            for id_type, id_val in id_numbers.items():
                if id_val and str(id_val).strip() and str(id_val) in full_text:
                    leaks.append(f"vault:id_number:{id_type}")

        raw_id = vault_dict.get("raw_national_id")
        if raw_id and str(raw_id).strip() and str(raw_id) in full_text:
            leaks.append("vault:raw_national_id")

        # Check address
        raw_addr = vault_dict.get("address") or vault_dict.get("raw_address")
        if raw_addr and len(str(raw_addr).strip()) > 5 and str(raw_addr).lower() in full_text.lower():
            leaks.append("vault:address")

        # Check DOB
        raw_dob = vault_dict.get("dob") or vault_dict.get("raw_dob")
        if raw_dob and str(raw_dob).strip() and str(raw_dob) in full_text:
            leaks.append("vault:dob")

    # Also check generic DOB regex if full_text contains a date
    if not leaks and DOB_REGEX.search(full_text) and "dob" in str(args).lower():
        leaks.append("date_of_birth")

    if leaks:
        event = GuardrailEvent(
            event_id=str(uuid.uuid4()),
            stage="tool_input",
            category="pii_leak",
            action="blocked",
            agent_id=agent_id,
            score=1.0,
            detail=f"Blocked outbound call to '{tool_name}': contains sensitive PII [{', '.join(leaks)}]",
        )
        return (
            PiiGuardResult(
                is_safe=False,
                leaked_fields=leaks,
                detail=f"Sensitive PII detected: {', '.join(leaks)}",
                action="blocked",
            ),
            event,
        )

    clean_event = GuardrailEvent(
        event_id=str(uuid.uuid4()),
        stage="tool_input",
        category="clean",
        action="allowed",
        agent_id=agent_id,
        score=0.0,
        detail=f"Outbound call to '{tool_name}' verified clean.",
    )
    return PiiGuardResult(is_safe=True, leaked_fields=[], detail="Clean", action="allowed"), clean_event
