"""Tests for all 4 combinations of messaging Mode and execution Pattern.

Per docs/06_IMPLEMENTATION_PLAN.md T14:
- (BLACKBOARD, SEQUENTIAL)
- (BLACKBOARD, PARALLEL)
- (HYBRID_P2P, SEQUENTIAL)
- (HYBRID_P2P, PARALLEL)
All 4 combinations must produce equivalent reports with valid OnboardingReport schema.
"""

from pathlib import Path

import pytest

from onboardiq.agents.adk.orchestrator import Orchestrator
from onboardiq.blackboard.client import BlackboardClient
from onboardiq.blackboard.service import app
from onboardiq.blackboard.store import SQLiteBlackboardStore
from onboardiq.schema import (
    LabelledCase,
    Mode,
    OnboardingReport,
    Pattern,
    RunConfig,
)


@pytest.mark.parametrize(
    "mode,pattern",
    [
        (Mode.BLACKBOARD, Pattern.SEQUENTIAL),
        (Mode.BLACKBOARD, Pattern.PARALLEL),
        (Mode.HYBRID_P2P, Pattern.SEQUENTIAL),
        (Mode.HYBRID_P2P, Pattern.PARALLEL),
    ],
)
def test_all_mode_and_pattern_combinations(mode: Mode, pattern: Pattern):
    case_path = Path("data/cases/case_001.json")
    with open(case_path, encoding="utf-8") as f:
        case = LabelledCase.model_validate_json(f.read())

    app.state.store = SQLiteBlackboardStore(db_path=":memory:")
    client = BlackboardClient(base_url="http://testserver", app=app)
    orch = Orchestrator()

    config = RunConfig(
        case_id=case.case_id,
        mode=mode,
        pattern=pattern,
    )

    report = orch.run_case(
        case=case,
        board_client=client,
        config=config,
    )

    # 1. Valid OnboardingReport schema
    assert isinstance(report, OnboardingReport)
    assert report.mode == mode
    assert report.pattern == pattern

    # 2. Correct decision & risk tier
    assert report.decision.value == "approve"
    assert report.risk_tier.value == "low"
    assert report.total_runtime_s > 0
    assert len(report.per_agent) >= 4
    assert not report.pii_leak_detected

