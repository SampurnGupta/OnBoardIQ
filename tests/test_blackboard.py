"""Tests for Blackboard Service (T03 acceptance).

Covers:
- create run and read it back
- write to a zone and read it back
- 403 on forbidden zone with access_denied GuardrailEvent logged in system zone
- 409 on stale expected_version
- event log ordering
"""

import pytest
from fastapi.testclient import TestClient

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
    PiiVault,
    Reasoning,
)


@pytest.fixture
def test_client():
    # Use isolated in-memory store for each test
    app.state.store = SQLiteBlackboardStore(db_path=":memory:")
    client = TestClient(app)
    return client


def _create_sample_blackboard(run_id: str = "run_test_001") -> Blackboard:
    profile = MaskedProfile(
        case_id="case_001",
        client_type=ClientType.INDIVIDUAL,
        display_name="John Doe",
        country="IN",
        source_of_funds="business",
        expected_monthly_volume_inr=100000.0,
    )
    pii = PiiVault(
        raw_name="Johnathonathan Doe",
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


def test_create_and_get_run(test_client):
    board = _create_sample_blackboard()
    create_resp = test_client.post(
        "/runs",
        content=board.model_dump_json(),
        headers={"Content-Type": "application/json"},
    )
    assert create_resp.status_code == 201
    created_data = create_resp.json()
    assert created_data["run_id"] == "run_test_001"
    assert created_data["version"] == 0

    get_resp = test_client.get(
        "/runs/run_test_001",
        headers={"X-Agent-ID": "adk.orchestrator"},
    )
    assert get_resp.status_code == 200
    fetched_data = get_resp.json()
    assert fetched_data["run_id"] == "run_test_001"
    # Orchestrator does not have access to pii_vault, so it should be masked
    assert fetched_data["pii_vault"]["raw_name"] == "***"


def test_zone_read_write(test_client):
    board = _create_sample_blackboard()
    create_resp = test_client.post("/runs", json=board.model_dump(mode="json"))
    assert create_resp.status_code == 201

    # adk.extractor has write access to 'verification'
    write_resp = test_client.post(
        "/runs/run_test_001/events",
        json={
            "agent_id": "adk.extractor",
            "zone": "verification",
            "op": "replace",
            "payload": {
                "checks": [
                    {
                        "check_id": "chk_01",
                        "check_type": "name_match",
                        "passed": True,
                        "similarity": 0.98,
                        "detail": "High confidence match",
                        "evidence": {
                            "evidence_id": "ev_01",
                            "agent_id": "adk.extractor",
                        },
                    }
                ]
            },
            "expected_version": 0,
        },
    )
    assert write_resp.status_code == 200
    assert write_resp.json()["version"] == 1

    # crewai.identity_verifier has read access to verification zone
    zone_resp = test_client.get(
        "/runs/run_test_001/zones/verification",
        headers={"X-Agent-ID": "crewai.identity_verifier"},
    )
    assert zone_resp.status_code == 200
    checks = zone_resp.json()["checks"]
    assert len(checks) == 1
    assert checks[0]["check_id"] == "chk_01"


def test_forbidden_zone_returns_403_and_logs_guardrail_event(test_client):
    board = _create_sample_blackboard()
    create_resp = test_client.post("/runs", json=board.model_dump(mode="json"))
    assert create_resp.status_code == 201

    # crewai.sanctions_screener tries to write to pii_vault (forbidden)
    forbidden_write = test_client.post(
        "/runs/run_test_001/events",
        json={
            "agent_id": "crewai.sanctions_screener",
            "zone": "pii_vault",
            "op": "replace",
            "payload": {"raw_name": "Hacked"},
            "expected_version": 0,
        },
    )
    assert forbidden_write.status_code == 403

    # Check that a GuardrailEvent of category access_denied was recorded in system zone
    system_zone_resp = test_client.get(
        "/runs/run_test_001/zones/system",
        headers={"X-Agent-ID": "admin"},
    )
    assert system_zone_resp.status_code == 200
    guardrail_events = system_zone_resp.json()["guardrail_events"]
    assert len(guardrail_events) >= 1
    denied_event = guardrail_events[-1]
    assert denied_event["category"] == "access_denied"
    assert denied_event["agent_id"] == "crewai.sanctions_screener"
    assert denied_event["action"] == "blocked"


def test_optimistic_concurrency_409(test_client):
    board = _create_sample_blackboard()
    create_resp = test_client.post("/runs", json=board.model_dump(mode="json"))
    assert create_resp.status_code == 201

    # First write at expected_version=0 succeeds -> version becomes 1
    resp1 = test_client.post(
        "/runs/run_test_001/events",
        json={
            "agent_id": "adk.orchestrator",
            "zone": "risk",
            "op": "replace",
            "payload": {},
            "expected_version": 0,
        },
    )
    assert resp1.status_code == 200
    assert resp1.json()["version"] == 1

    # Stale write with expected_version=0 should fail with 409
    resp2 = test_client.post(
        "/runs/run_test_001/events",
        json={
            "agent_id": "adk.orchestrator",
            "zone": "risk",
            "op": "replace",
            "payload": {},
            "expected_version": 0,
        },
    )
    assert resp2.status_code == 409
    assert "Version conflict" in resp2.json()["detail"]


def test_event_log_ordering(test_client):
    board = _create_sample_blackboard()
    create_resp = test_client.post("/runs", json=board.model_dump(mode="json"))
    assert create_resp.status_code == 201

    # Sequence of writes
    test_client.post(
        "/runs/run_test_001/events",
        json={
            "agent_id": "adk.extractor",
            "zone": "verification",
            "op": "replace",
            "payload": {"checks": []},
            "expected_version": 0,
        },
    )
    test_client.post(
        "/runs/run_test_001/events",
        json={
            "agent_id": "crewai.sanctions_screener",
            "zone": "screening",
            "op": "replace",
            "payload": {"hits": []},
            "expected_version": 1,
        },
    )

    events_resp = test_client.get("/runs/run_test_001/events")
    assert events_resp.status_code == 200
    events = events_resp.json()

    # Initial event + 2 updates = 3 events
    assert len(events) == 3
    assert events[0]["op"] == "init"
    assert events[0]["version"] == 0
    assert events[1]["agent_id"] == "adk.extractor"
    assert events[1]["version"] == 1
    assert events[2]["agent_id"] == "crewai.sanctions_screener"
    assert events[2]["version"] == 2


@pytest.mark.asyncio
async def test_blackboard_client(test_client):
    from httpx import ASGITransport

    from onboardiq.blackboard.client import BlackboardClient

    transport = ASGITransport(app=app)
    client = BlackboardClient(
        base_url="http://testserver",
        agent_id="adk.orchestrator",
        transport=transport,
    )

    board = _create_sample_blackboard("run_client_001")
    created = await client.acreate_run(board)
    assert created.run_id == "run_client_001"

    fetched = await client.aget_run("run_client_001")
    assert fetched.run_id == "run_client_001"

    # Orchestrator appends event to risk zone
    res = await client.aappend_event(
        run_id="run_client_001",
        zone="risk",
        payload={},
        expected_version=0,
    )
    assert res["status"] == "applied"
    assert res["version"] == 1

    events = await client.aget_events("run_client_001")
    assert len(events) == 2
