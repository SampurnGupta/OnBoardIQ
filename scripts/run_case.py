"""CLI script to run OnboardIQ end-to-end on any benchmark case.

Usage:
    python scripts/run_case.py --case case_001
    python scripts/run_case.py --case data/cases/case_008.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from onboardiq.agents.adk.orchestrator import Orchestrator
from onboardiq.blackboard.client import BlackboardClient
from onboardiq.blackboard.service import app as bb_app
from onboardiq.blackboard.store import SQLiteBlackboardStore
from onboardiq.schema import LabelledCase

ROOT_DIR = Path(__file__).resolve().parents[1]


def run_case_cli(case_identifier: str, use_a2a: bool = False):
    # Resolve case path
    if case_identifier.endswith(".json"):
        case_path = Path(case_identifier)
        if not case_path.is_absolute():
            case_path = ROOT_DIR / case_identifier
    else:
        # e.g. case_001
        case_path = ROOT_DIR / "data" / "cases" / f"{case_identifier}.json"

    if not case_path.exists():
        raise FileNotFoundError(f"Case file {case_path} does not exist.")

    case = LabelledCase.model_validate_json(case_path.read_text(encoding="utf-8"))

    # Setup blackboard
    bb_app.state.store = SQLiteBlackboardStore(db_path=":memory:")
    board_client = BlackboardClient(base_url="http://testserver", app=bb_app)

    orchestrator = Orchestrator()
    report = orchestrator.run_case(case=case, board_client=board_client, use_a2a=use_a2a)

    print("\n" + "=" * 60)
    print(f"CASE RUN RESULT: {case.case_id} ({case.declared_name})")
    print("=" * 60)
    print(report.summary_markdown)
    print("\nREPORT JSON:")
    print(json.dumps(report.model_dump(mode="json"), indent=2))
    return report


def main():
    parser = argparse.ArgumentParser(description="Run OnboardIQ Onboarding Case")
    parser.add_argument("--case", required=True, help="Case identifier (e.g. case_001) or path to JSON")
    parser.add_argument("--a2a", action="store_true", help="Dispatch screening over remote A2A endpoint")
    args = parser.parse_args()

    run_case_cli(args.case, use_a2a=args.a2a)


if __name__ == "__main__":
    main()

