"""Tests for Parallel Pattern execution and concurrent blackboard writes.

Per docs/06_IMPLEMENTATION_PLAN.md T13.
"""

import concurrent.futures
from pathlib import Path

from onboardiq.agents.adk.orchestrator import Orchestrator
from onboardiq.blackboard.client import BlackboardClient
from onboardiq.blackboard.service import app
from onboardiq.blackboard.store import SQLiteBlackboardStore
from onboardiq.schema import (
    Blackboard,
    ClientType,
    IntakeZone,
    LabelledCase,
    MaskedProfile,
    Mode,
    Pattern,
    Persona,
    Phase,
    PiiVault,
    Reasoning,
    RunConfig,
)
from onboardiq.telemetry.callbacks import create_step_trace


def test_concurrent_blackboard_writes_with_retry():
    """Verify that multiple concurrent threads writing to blackboard handle 409 and all succeed."""
    app.state.store = SQLiteBlackboardStore(db_path=":memory:")
    client = BlackboardClient(base_url="http://testserver", app=app)

    board = Blackboard(
        run_id="run_concurrency_test",
        case_id="case_001",
        mode=Mode.BLACKBOARD,
        pattern=Pattern.PARALLEL,
        reasoning=Reasoning.PLAIN,
        persona=Persona.COOPERATIVE,
        intake=IntakeZone(
            profile=MaskedProfile(
                case_id="case_001",
                client_type=ClientType.INDIVIDUAL,
                display_name="Concurrency User",
                country="IN",
                source_of_funds="Salary",
                expected_monthly_volume_inr=50000.0,
            )
        ),
        pii_vault=PiiVault(raw_name="Concurrency User", address="Mumbai"),
    )
    client.create_run(board)

    # 5 concurrent threads attempting to append events to the system zone simultaneously
    def writer_worker(idx: int) -> int:
        trace = create_step_trace(
            agent_id="adk.orchestrator",
            phase=Phase.INTAKE,
            step_type="tool",
            name=f"worker_{idx}",
            latency_ms=10.0,
        )
        _, new_v = client.append_event_with_retry(
            run_id="run_concurrency_test",
            zone="system",
            payload={"field": "traces", "item": trace.model_dump(mode="json")},
            expected_version=0,
            op="append",
            agent_id="telemetry",
            max_retries=10,
        )
        return new_v

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(writer_worker, i) for i in range(5)]
        results = [f.result() for f in futures]

    assert len(results) == 5

    final_board = client.get_run("run_concurrency_test", agent_id="adk.orchestrator")
    assert final_board.version == 5
    assert len(final_board.system.traces) == 5


def test_sequential_vs_parallel_report_equivalence():
    """Verify that Sequential and Parallel patterns yield equivalent reports on the same case."""
    case_path = Path("data/cases/case_001.json")
    with open(case_path, encoding="utf-8") as f:
        case = LabelledCase.model_validate_json(f.read())

    # 1. Run Sequential
    app.state.store = SQLiteBlackboardStore(db_path=":memory:")
    client_seq = BlackboardClient(base_url="http://testserver", app=app)
    orch = Orchestrator()
    report_seq = orch.run_case(
        case=case,
        board_client=client_seq,
        config=RunConfig(case_id=case.case_id, pattern=Pattern.SEQUENTIAL),
    )

    # 2. Run Parallel
    app.state.store = SQLiteBlackboardStore(db_path=":memory:")
    client_par = BlackboardClient(base_url="http://testserver", app=app)
    report_par = orch.run_case(
        case=case,
        board_client=client_par,
        config=RunConfig(case_id=case.case_id, pattern=Pattern.PARALLEL),
    )

    # Equivalence checks:
    assert report_seq.decision == report_par.decision
    assert report_seq.risk_tier == report_par.risk_tier
    assert abs(report_seq.risk_score - report_par.risk_score) < 1e-4
    assert len(report_seq.red_flags) == len(report_par.red_flags)
    assert report_seq.sanctions_or_pep_hits == report_par.sanctions_or_pep_hits
    assert report_seq.pii_leak_detected == report_par.pii_leak_detected

    # Both produce valid schemas
    assert report_seq.pattern == Pattern.SEQUENTIAL
    assert report_par.pattern == Pattern.PARALLEL
