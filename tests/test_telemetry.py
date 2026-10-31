"""Tests for telemetry, cost estimation, and trace logging."""

from onboardiq.blackboard.client import BlackboardClient
from onboardiq.blackboard.service import app
from onboardiq.blackboard.store import SQLiteBlackboardStore
from onboardiq.schema import (
    Blackboard,
    ClientType,
    IntakeZone,
    MaskedProfile,
    Mode,
    Pattern,
    Persona,
    Phase,
    PiiVault,
    Reasoning,
)
from onboardiq.telemetry.callbacks import create_step_trace, record_step_trace
from onboardiq.telemetry.cost import estimate_cost


def test_estimate_cost():
    # 1,000,000 prompt tokens + 1,000,000 completion tokens on gemini-2.5-flash
    # input rate: $0.15, output rate: $0.60 -> total $0.75
    cost = estimate_cost("gemini-2.5-flash", 1_000_000, 1_000_000)
    assert abs(cost - 0.75) < 1e-4

    # 1000 tokens each
    cost_small = estimate_cost("gemini-2.5-flash", 1_000, 1_000)
    assert cost_small > 0.0
    assert cost_small < 0.01

    # zero tokens
    assert estimate_cost("gemini-2.5-flash", 0, 0) == 0.0


def test_step_trace_creation_and_recording():
    app.state.store = SQLiteBlackboardStore(db_path=":memory:")
    client = BlackboardClient(base_url="http://testserver", app=app)

    board = Blackboard(
        run_id="run_telemetry_test",
        case_id="case_001",
        mode=Mode.BLACKBOARD,
        pattern=Pattern.SEQUENTIAL,
        reasoning=Reasoning.REACT,
        persona=Persona.COOPERATIVE,
        intake=IntakeZone(
            profile=MaskedProfile(
                case_id="case_001",
                client_type=ClientType.INDIVIDUAL,
                display_name="Test User",
                country="IN",
                source_of_funds="Salary",
                expected_monthly_volume_inr=10000.0,
            )
        ),
        pii_vault=PiiVault(raw_name="Test User", address="Test Address"),
    )
    client.create_run(board)

    # 1. Direct step trace creation
    trace = create_step_trace(
        agent_id="adk.gateway",
        phase=Phase.INTAKE,
        step_type="model",
        name="sanitize_intake",
        latency_ms=120.5,
        prompt_tokens=250,
        completion_tokens=100,
        cost_usd=0.0001,
    )
    assert trace.agent_id == "adk.gateway"
    assert trace.framework == "adk"
    assert trace.latency_ms == 120.5
    assert trace.prompt_tokens == 250
    assert trace.completion_tokens == 100

    # 2. Record step trace onto blackboard
    logged_trace, new_ver = record_step_trace(
        board_client=client,
        run_id="run_telemetry_test",
        agent_id="crewai.sanctions_screener",
        phase=Phase.SCREENING,
        step_type="tool",
        name="sanctions_screen",
        latency_ms=45.0,
        prompt_tokens=150,
        completion_tokens=50,
        current_version=0,
    )
    assert logged_trace.agent_id == "crewai.sanctions_screener"
    assert logged_trace.framework == "crewai"
    assert new_ver == 1

    # Verify presence in blackboard system zone
    updated_board = client.get_run("run_telemetry_test", agent_id="adk.orchestrator")
    assert len(updated_board.system.traces) == 1
    assert updated_board.system.traces[0].name == "sanctions_screen"
    assert updated_board.system.traces[0].framework == "crewai"
