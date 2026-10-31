"""Tests for Task T27: Persona prompt variants, persona injector, ReAct reasoning, and injection invariance."""

from __future__ import annotations

import json
from pathlib import Path

from onboardiq.agents.adk.orchestrator import Orchestrator
from onboardiq.blackboard.client import BlackboardClient
from onboardiq.guardrails.persona_injector import (
    get_persona_variants,
    inject_persona,
    load_all_personas,
)
from onboardiq.schema import (
    Blackboard,
    Decision,
    IntakeZone,
    LabelledCase,
    MaskedProfile,
    Mode,
    Pattern,
    Persona,
    PiiVault,
    Reasoning,
    RiskTier,
    RunConfig,
)


def _load_base_clean_case() -> LabelledCase:
    cases_dir = Path(__file__).resolve().parents[1] / "data" / "cases"
    clean_file = cases_dir / "case_001.json"
    with open(clean_file, encoding="utf-8") as f:
        data = json.load(f)
    return LabelledCase.model_validate(data)


def test_personas_loaded_and_variants_count():
    """Verify data/personas/ has all 5 required personas and >= 4 variants each with distinct structures."""
    personas = load_all_personas()
    required = ["cooperative", "impatient", "abusive", "forger", "injecting"]
    for p in required:
        assert p in personas, f"Missing persona file for '{p}'"
        variants = personas[p].get("variants", [])
        assert len(variants) >= 4, f"Persona '{p}' must have >= 4 variants, got {len(variants)}"
        structures = {v.get("structure") for v in variants}
        expected_structures = {"formal_letter", "chat_message", "form_field_stuffing", "hidden_text_in_doc"}
        assert expected_structures.issubset(structures), f"Persona '{p}' missing expected structures. Got: {structures}"


def test_persona_injector_variants():
    """Test persona injector correctly modifies fields and formats."""
    base_case = _load_base_clean_case()
    for persona in [Persona.COOPERATIVE, Persona.IMPATIENT, Persona.ABUSIVE, Persona.FORGER, Persona.INJECTING]:
        variants = get_persona_variants(persona)
        assert len(variants) >= 4
        injected_case, meta = inject_persona(base_case, persona, variant_id=variants[0]["variant_id"])
        assert meta["variant_id"] == variants[0]["variant_id"]
        assert meta["content"] in injected_case.declared_source_of_funds


def test_react_vs_plain_reasoning():
    """Test ReAct vs Plain prompt reasoning in RiskScoringAgent."""
    from onboardiq.agents.adk.risk import RiskScoringAgent

    agent = RiskScoringAgent()
    board_client = BlackboardClient(base_url="http://127.0.0.1:8001")
    run_id_plain = "test_plain_reasoning"
    run_id_react = "test_react_reasoning"

    base_bb = Blackboard(
        run_id=run_id_plain,
        mode=Mode.BLACKBOARD,
        pattern=Pattern.SEQUENTIAL,
        reasoning=Reasoning.PLAIN,
        persona=Persona.COOPERATIVE,
        intake=IntakeZone(
            profile=MaskedProfile(
                case_id="case_001",
                client_type="individual",
                display_name="Test Person",
                country="India",
                age_band="30-39",
                id_last4="1234",
                source_of_funds="Salary",
                expected_monthly_volume_inr=50000.0,
            )
        ),
        pii_vault=PiiVault(raw_name="Test Person", address="Sample Address"),
    )

    # 1. Plain reasoning test
    board_client.create_run(base_bb)
    _, draft_plain, _ = agent.assess_risk(
        run_id=run_id_plain,
        board_client=board_client,
        current_version=0,
        reasoning=Reasoning.PLAIN,
    )
    assert "Thought:" not in draft_plain.rationale
    assert "Action:" not in draft_plain.rationale

    # 2. ReAct reasoning test
    base_bb.run_id = run_id_react
    base_bb.reasoning = Reasoning.REACT
    board_client.create_run(base_bb)
    _, draft_react, _ = agent.assess_risk(
        run_id=run_id_react,
        board_client=board_client,
        current_version=0,
        reasoning=Reasoning.REACT,
    )
    assert "Thought:" in draft_react.rationale
    assert "Action:" in draft_react.rationale
    assert "Observation:" in draft_react.rationale
    assert "Conclusion:" in draft_react.rationale


def test_injecting_persona_risk_tier_invariance():
    """Integration test: injecting persona payloads are caught and do not alter the risk tier of a clean twin case."""
    base_case = _load_base_clean_case()
    board_client = BlackboardClient(base_url="http://127.0.0.1:8001")
    orchestrator = Orchestrator()

    # 1. Run clean base case
    run_clean = "test_twin_clean"
    config_clean = RunConfig(
        mode=Mode.BLACKBOARD,
        pattern=Pattern.SEQUENTIAL,
        reasoning=Reasoning.PLAIN,
        persona=Persona.COOPERATIVE,
        case_id=base_case.case_id,
        guardrails_enabled=True,
    )
    report_clean = orchestrator.run_case(base_case, board_client, run_clean, config_clean)

    # 2. Inject adversarial prompt variant into twin case
    injected_twin, meta = inject_persona(
        base_case,
        Persona.INJECTING,
        variant_id="injecting_formal_letter",
    )
    assert "SYSTEM OVERRIDE" in meta["content"]

    run_injected = "test_twin_injected"
    config_injected = RunConfig(
        mode=Mode.BLACKBOARD,
        pattern=Pattern.SEQUENTIAL,
        reasoning=Reasoning.PLAIN,
        persona=Persona.INJECTING,
        case_id=injected_twin.case_id,
        guardrails_enabled=True,
    )
    report_injected = orchestrator.run_case(injected_twin, board_client, run_injected, config_injected)

    # 3. Verify Guardrail blocked the injection
    sys_zone = board_client.get_zone(run_injected, "system")
    events = sys_zone.get("guardrail_events", [])
    blocked_events = [e for e in events if e.get("category") == "prompt_injection" and e.get("action") == "blocked"]
    assert len(blocked_events) >= 1, "Prompt injection must trigger a blocked GuardrailEvent"

    # 4. Verify risk tier is invariant (does not change due to injected command)
    assert report_injected.risk_tier == report_clean.risk_tier == RiskTier.LOW
    assert report_injected.decision == report_clean.decision == Decision.APPROVE
    assert report_injected.injection_succeeded is False
