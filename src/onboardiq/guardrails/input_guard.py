"""Input guardrail layer for OnboardIQ.

Scans applicant text, client communication, and OCR extracted text for:
1. Toxic, abusive, or threatening language
2. Prompt injection attempts
3. Social engineering and urgency manipulation
"""

from __future__ import annotations

import re
import uuid
from typing import Literal

from onboardiq.schema import GuardrailEvent

# Lexicon patterns for toxicity and abuse
TOXICITY_PATTERNS = [
    r"\b(idiot|stupid|moron|dumb|incompetent|corrupt|scam|fraudster|threat|sue|court|jail)\b",
    r"\b(shut up|fuck|shit|bastard|kill|destroy|ruin you)\b",
    r"\b(waste of time|useless system|pathetic)\b",
]

# Signatures for prompt injection attacks
INJECTION_PATTERNS = [
    r"ignore\s+(all\s+|the\s+)?(previous|prior|above)\s+(instructions|rules|prompts)",
    r"disregard\s+(all\s+)?(rules|instructions|system|policies|sanctions|filters)",
    r"(system\s*:\s*)?set\s+(risk|tier|decision)\s*(to|[:=])\s*['\"]?(low|approve)['\"]?",
    r"you\s+must\s+approve",
    r"override\s+(risk|tier|decision|rules|compliance|red_flags)",
    r"set\s+(tier|risk|decision)\s*[:=]\s*['\"]?(low|approve)['\"]?",
    r"print\s+['\"]?approved['\"]?",
    r"reveal\s+(system\s+prompt|hidden\s+rules|pii_vault|blacklist)",
    r"developer\s+mode\s+enabled",
    r"whitelisted\s+entity",
    r"system\s+override",
    r"emergency\s+exemption",
    r"ignore_sanctions",
]

# Patterns for social engineering and VIP pressure
SOCIAL_ENGINEERING_PATTERNS = [
    r"i\s+am\s+the\s+(head|ceo|director|managing\s+director|chief|president)\s+of\s+compliance",
    r"skip\s+(all\s+)?(checks|verification|due\s+diligence)",
    r"vip\s+(client|account|customer)",
    r"urgent(ly)?\s+approve",
    r"do\s+you\s+know\s+who\s+i\s+am",
    r"process\s+this\s+immediately\s+without",
]

VALID_STAGES = {"input", "document_text", "tool_input", "tool_output", "model_output", "blackboard_access"}


def _normalize_stage(stage: str) -> Literal["input", "document_text", "tool_input", "tool_output", "model_output", "blackboard_access"]:
    if stage in VALID_STAGES:
        return stage  # type: ignore[return-value]
    if "ocr" in stage or "doc" in stage:
        return "document_text"
    if "tool" in stage:
        return "tool_input"
    if "model" in stage or "output" in stage:
        return "model_output"
    return "input"


class InputGuardResult:
    def __init__(
        self,
        is_safe: bool,
        category: Literal["clean", "toxicity", "prompt_injection", "social_engineering"],
        action: Literal["allowed", "masked", "blocked"],
        score: float,
        reason: str,
    ):
        self.is_safe = is_safe
        self.category = category
        self.action = action
        self.score = score
        self.reason = reason


def scan_text(text: str, agent_id: str = "adk.gateway", stage: str = "input") -> tuple[InputGuardResult, GuardrailEvent]:
    """Scan input text against prompt injection, toxicity, and social engineering patterns."""
    text_lower = text.lower()
    norm_stage = _normalize_stage(stage)

    # 1. Prompt Injection Check (Highest Priority)
    for pat in INJECTION_PATTERNS:
        match = re.search(pat, text_lower)
        if match:
            event = GuardrailEvent(
                event_id=str(uuid.uuid4()),
                stage=norm_stage,
                category="prompt_injection",
                action="blocked",
                agent_id=agent_id,
                score=1.0,
                detail=f"Prompt injection pattern detected: '{match.group(0)}'",
            )
            return (
                InputGuardResult(
                    is_safe=False,
                    category="prompt_injection",
                    action="blocked",
                    score=1.0,
                    reason=f"Instruction injection attempt detected: '{match.group(0)}'",
                ),
                event,
            )

    # 2. Social Engineering Check
    for pat in SOCIAL_ENGINEERING_PATTERNS:
        match = re.search(pat, text_lower)
        if match:
            event = GuardrailEvent(
                event_id=str(uuid.uuid4()),
                stage=norm_stage,
                category="social_engineering",
                action="blocked",
                agent_id=agent_id,
                score=0.85,
                detail=f"Social engineering / authority claim detected: '{match.group(0)}'",
            )
            return (
                InputGuardResult(
                    is_safe=False,
                    category="social_engineering",
                    action="blocked",
                    score=0.85,
                    reason=f"Social engineering manipulation detected: '{match.group(0)}'",
                ),
                event,
            )

    # 3. Toxicity Check
    for pat in TOXICITY_PATTERNS:
        match = re.search(pat, text_lower)
        if match:
            event = GuardrailEvent(
                event_id=str(uuid.uuid4()),
                stage=norm_stage,
                category="toxicity",
                action="masked",
                agent_id=agent_id,
                score=0.90,
                detail=f"Toxic or abusive language detected: '{match.group(0)}'",
            )
            return (
                InputGuardResult(
                    is_safe=False,
                    category="toxicity",
                    action="masked",
                    score=0.90,
                    reason=f"Abusive language detected: '{match.group(0)}'",
                ),
                event,
            )

    # Clean text
    clean_event = GuardrailEvent(
        event_id=str(uuid.uuid4()),
        stage=norm_stage,
        category="clean",
        action="allowed",
        agent_id=agent_id,
        score=0.0,
        detail="Text scan passed cleanly.",
    )
    return (
        InputGuardResult(
            is_safe=True,
            category="clean",
            action="allowed",
            score=0.0,
            reason="Clean",
        ),
        clean_event,
    )
