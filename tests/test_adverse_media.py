"""Unit and integration tests for Adverse Media Agent and news_search FastMCP tool."""

from __future__ import annotations

from pathlib import Path

from onboardiq.agents.adk.orchestrator import Orchestrator
from onboardiq.agents.crewai.screening_crew import AdverseMediaAnalystAgent
from onboardiq.blackboard.client import BlackboardClient
from onboardiq.blackboard.service import app
from onboardiq.blackboard.store import SQLiteBlackboardStore
from onboardiq.mcp_server.tools.news_search import news_search
from onboardiq.schema import (
    Blackboard,
    ClientType,
    IntakeZone,
    LabelledCase,
    MaskedProfile,
    Mode,
    Pattern,
    Persona,
    PiiVault,
    Reasoning,
    RunConfig,
)


def _get_test_client() -> BlackboardClient:
    app.state.store = SQLiteBlackboardStore(db_path=":memory:")
    return BlackboardClient(base_url="http://testserver", app=app, agent_id="admin")


def _make_sample_blackboard(run_id: str, name: str) -> Blackboard:
    profile = MaskedProfile(
        case_id="case_test",
        client_type=ClientType.INDIVIDUAL,
        display_name=name,
        country="IN",
        source_of_funds="business",
        expected_monthly_volume_inr=100000.0,
    )
    pii = PiiVault(
        raw_name=name,
        dob="1985-04-12",
        address="123 Financial District, Mumbai",
        id_numbers={"pan": "ABCDE1234F"},
    )
    return Blackboard(
        run_id=run_id,
        version=0,
        mode=Mode.BLACKBOARD,
        pattern=Pattern.SEQUENTIAL,
        reasoning=Reasoning.PLAIN,
        persona=Persona.COOPERATIVE,
        intake=IntakeZone(profile=profile),
        pii_vault=pii,
    )


def test_news_search_tool_three_corpus_examples():
    """Verify the 3 corpus examples: Relevant (money laundering), Namesake (minor/other), and Clean."""
    # 1. Relevant adverse media
    res_rel = news_search(query="Sanjay V. Verma")
    assert res_rel["count"] >= 1
    art_rel = res_rel["articles"][0]
    assert art_rel["category"] == "money_laundering"
    assert art_rel["match_score"] >= 0.80
    assert "hawala" in art_rel["summary"].lower() or "money laundering" in art_rel["summary"].lower()

    # 2. Namesake / minor citation
    res_name = news_search(query="Arun Kumar Patel")
    assert res_name["count"] >= 1
    art_name = res_name["articles"][0]
    assert art_name["category"] == "other"

    # 3. Clean / None
    res_clean = news_search(query="Priya Rajesh Sharma")
    assert res_clean["count"] == 0
    assert len(res_clean["articles"]) == 0


def test_adverse_media_analyst_relevant_hit():
    """Test that a relevant money laundering article creates a MediaFinding and raises an adverse_media red flag."""
    client = _get_test_client()
    board = client.create_run(_make_sample_blackboard("run_test_media_rel", "Sanjay V. Verma"))
    current_ver = board.version

    analyst = AdverseMediaAnalystAgent()
    findings, red_flags, _ = analyst.analyze_media(
        run_id="run_test_media_rel",
        board_client=client,
        current_version=current_ver,
    )

    assert len(findings) >= 1
    finding = findings[0]
    assert finding.category == "money_laundering"
    assert finding.relevance >= 0.70
    assert finding.evidence.tool == "news_search"
    assert "Enforcement Directorate" in finding.summary

    # Ensure red flag was raised
    media_flags = [f for f in red_flags if f.flag_type == "adverse_media"]
    assert len(media_flags) == 1
    assert media_flags[0].severity == "high"
    assert finding.finding_id in media_flags[0].evidence_ids

    # Verify blackboard screening zone was updated
    scr_zone = client.get_zone("run_test_media_rel", "screening")
    assert len(scr_zone.get("media", [])) >= 1
    assert any(f.get("flag_type") == "adverse_media" for f in scr_zone.get("red_flags", []))


def test_adverse_media_analyst_namesake_no_red_flag():
    """Test that a namesake article gets low relevance and does NOT raise an adverse_media red flag."""
    client = _get_test_client()
    board = client.create_run(_make_sample_blackboard("run_test_media_name", "Arun Kumar Patel"))
    current_ver = board.version

    analyst = AdverseMediaAnalystAgent()
    findings, red_flags, _ = analyst.analyze_media(
        run_id="run_test_media_name",
        board_client=client,
        current_version=current_ver,
    )

    assert len(findings) >= 1
    finding = findings[0]
    assert finding.category == "other"
    assert finding.relevance <= 0.30  # Low relevance disambiguation

    # Crucial: NO adverse_media red flag should be raised for namesake
    media_flags = [f for f in red_flags if f.flag_type == "adverse_media"]
    assert len(media_flags) == 0


def test_adverse_media_analyst_clean_case():
    """Test that a clean subject produces zero adverse findings."""
    client = _get_test_client()
    board = client.create_run(_make_sample_blackboard("run_test_media_clean", "Priya Rajesh Sharma"))
    current_ver = board.version

    analyst = AdverseMediaAnalystAgent()
    findings, red_flags, _ = analyst.analyze_media(
        run_id="run_test_media_clean",
        board_client=client,
        current_version=current_ver,
    )

    assert len(findings) == 0
    assert len(red_flags) == 0


def test_orchestrator_parallel_and_sequential_with_media():
    """Test full pipeline execution in Sequential and Parallel patterns with media analyst."""
    orch = Orchestrator()

    case_path = Path("data/cases/case_005.json")
    with open(case_path, encoding="utf-8") as f:
        case = LabelledCase.model_validate_json(f.read())

    # 1. Sequential Run
    client_seq = _get_test_client()
    cfg_seq = RunConfig(case_id=case.case_id, mode=Mode.BLACKBOARD, pattern=Pattern.SEQUENTIAL)
    rep_seq = orch.run_case(case=case, board_client=client_seq, run_id="run_test_media_seq", config=cfg_seq)
    bb_seq = client_seq.get_run("run_test_media_seq", agent_id="admin")
    assert len(bb_seq.screening.media) >= 1
    assert any(f.flag_type == "adverse_media" for f in bb_seq.screening.red_flags)
    assert rep_seq.decision.value == "approve_with_enhanced_monitoring"

    # 2. Parallel Run
    client_par = _get_test_client()
    cfg_par = RunConfig(case_id=case.case_id, mode=Mode.BLACKBOARD, pattern=Pattern.PARALLEL)
    rep_par = orch.run_case(case=case, board_client=client_par, run_id="run_test_media_par", config=cfg_par)
    bb_par = client_par.get_run("run_test_media_par", agent_id="admin")
    assert len(bb_par.screening.media) >= 1
    assert any(f.flag_type == "adverse_media" for f in bb_par.screening.red_flags)
    assert rep_par.decision.value == "approve_with_enhanced_monitoring"

    # Equivalence checks:
    assert rep_seq.decision == rep_par.decision
    assert rep_seq.risk_tier == rep_par.risk_tier
