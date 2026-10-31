"""Tests for Task T32: Cloud Run deployment configs, Dockerfiles, and Firestore store."""

from __future__ import annotations

from pathlib import Path

import yaml

from onboardiq.blackboard.firestore_store import FirestoreBlackboardStore
from onboardiq.schema import (
    Blackboard,
    IntakeZone,
    MaskedProfile,
    Mode,
    Pattern,
    Persona,
    PiiVault,
    Reasoning,
)


def test_dockerfiles_exist():
    """Verify Dockerfiles exist for each microservice in deploy/."""
    deploy_dir = Path("deploy")
    required = [
        "Dockerfile.blackboard",
        "Dockerfile.mcp",
        "Dockerfile.screening",
        "Dockerfile.orchestrator",
        "Dockerfile.ui",
        "cloudrun.md",
    ]
    for req in required:
        file_path = deploy_dir / req
        assert file_path.exists(), f"Missing required deployment file: {req}"
        assert file_path.stat().st_size > 50


def test_docker_compose_validity():
    """Verify root docker-compose.yml is valid YAML and covers core services."""
    compose_path = Path("docker-compose.yml")
    assert compose_path.exists()
    with open(compose_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    services = data.get("services", {})
    assert "blackboard-svc" in services
    assert "mcp-tools" in services
    assert "screening-crewai" in services
    assert "ui" in services


def test_firestore_blackboard_store_mock_mode():
    """Verify FirestoreBlackboardStore creates runs and records events in mock fallback mode."""
    store = FirestoreBlackboardStore(project_id="test-onboardiq-project")
    run_id = "test_firestore_run_01"

    initial_board = Blackboard(
        run_id=run_id,
        mode=Mode.BLACKBOARD,
        pattern=Pattern.SEQUENTIAL,
        reasoning=Reasoning.PLAIN,
        persona=Persona.COOPERATIVE,
        intake=IntakeZone(
            profile=MaskedProfile(
                case_id="case_001",
                client_type="individual",
                display_name="Test Person",
                country="IN",
                source_of_funds="Salary",
                expected_monthly_volume_inr=50000.0,
            )
        ),
        pii_vault=PiiVault(raw_name="Test Person", address="Sample Address"),
    )

    created = store.create_run(initial_board)
    assert created.run_id == run_id

    fetched = store.get_run(run_id)
    assert fetched is not None
    assert fetched.run_id == run_id

    # Test event application and optimistic concurrency
    updated, evt = store.apply_event(
        run_id=run_id,
        agent_id="adk.gateway",
        zone="review",
        op="update",
        payload={"final_decision": "approve"},
        expected_version=0,
    )
    assert updated.version == 1
    assert evt["version"] == 1
    assert store.get_run(run_id).version == 1

    events = store.get_events(run_id)
    assert len(events) == 1

