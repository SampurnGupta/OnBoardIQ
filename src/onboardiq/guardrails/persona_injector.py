"""Persona injector module for OnboardIQ.

Loads persona variants from data/personas/ and injects them into LabelledCases
for evaluation sweeps, adversarial testing, and guardrail ablation studies.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from onboardiq.schema import LabelledCase, Persona

PERSONAS_DIR = Path(__file__).resolve().parents[3] / "data" / "personas"


def get_personas_dir() -> Path:
    """Return the resolved path to data/personas/."""
    return PERSONAS_DIR


def load_all_personas() -> dict[str, dict[str, Any]]:
    """Load all persona definitions and variants from data/personas/."""
    personas: dict[str, dict[str, Any]] = {}
    p_dir = get_personas_dir()
    if not p_dir.exists():
        return personas

    for json_file in p_dir.glob("*.json"):
        try:
            with open(json_file, encoding="utf-8") as f:
                data = json.load(f)
                name = data.get("persona", json_file.stem)
                personas[name] = data
        except (OSError, json.JSONDecodeError):
            continue
    return personas


def get_persona_variants(persona: Persona | str) -> list[dict[str, Any]]:
    """Return the list of variants for a given persona."""
    persona_key = persona.value if isinstance(persona, Persona) else str(persona).lower()
    personas = load_all_personas()
    if persona_key in personas:
        return personas[persona_key].get("variants", [])

    # Check directly from file if not loaded
    file_path = get_personas_dir() / f"{persona_key}.json"
    if file_path.exists():
        with open(file_path, encoding="utf-8") as f:
            data = json.load(f)
            return data.get("variants", [])
    return []


def inject_persona(
    case: LabelledCase,
    persona: Persona | str,
    variant_id: str | None = None,
    structure: str | None = None,
) -> tuple[LabelledCase, dict[str, Any]]:
    """Inject a persona variant into a base LabelledCase.

    Args:
        case: Base LabelledCase to clone and inject.
        persona: Target persona (cooperative, impatient, abusive, forger, injecting).
        variant_id: Optional exact variant ID to use.
        structure: Optional structure filter (formal_letter, chat_message, form_field_stuffing, hidden_text_in_doc).

    Returns:
        tuple of (injected_case, applied_variant_dict)
    """
    variants = get_persona_variants(persona)
    if not variants:
        # Fallback to no-op if persona variants not found
        return case.model_copy(deep=True), {"variant_id": "none", "content": ""}

    selected_variant: dict[str, Any] = variants[0]
    if variant_id:
        for v in variants:
            if v.get("variant_id") == variant_id:
                selected_variant = v
                break
    elif structure:
        for v in variants:
            if v.get("structure") == structure:
                selected_variant = v
                break

    target_field = selected_variant.get("target_field", "intake_message")
    content = selected_variant.get("content", "")

    # Deep copy the case
    case_dict = case.model_dump()

    # Apply the injection based on target field and structure
    orig_funds = case_dict.get("declared_source_of_funds", "")

    if target_field == "declared_source_of_funds":
        case_dict["declared_source_of_funds"] = f"{orig_funds}\n[Applicant Statement]: {content}"
    elif target_field == "intake_message":
        case_dict["declared_source_of_funds"] = f"{orig_funds}\n[Incoming Communication ({selected_variant.get('structure')}]: {content}"
    elif target_field == "doc_annotation":
        case_dict["declared_source_of_funds"] = f"{orig_funds}\n[Document Annotation]: {content}"
    else:
        case_dict["declared_source_of_funds"] = f"{orig_funds}\n[Note]: {content}"

    injected_case = LabelledCase.model_validate(case_dict)
    return injected_case, selected_variant
