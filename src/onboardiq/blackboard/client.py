"""Thin client for agents and MCP tools to interact with the Blackboard Service."""

from __future__ import annotations

from typing import Any

import httpx

from onboardiq.schema import Blackboard


class BlackboardClient:
    """HTTP client for the Blackboard Service."""

    def __init__(
        self,
        base_url: str = "http://localhost:8001",
        agent_id: str = "admin",
        service_token: str | None = None,
        timeout: float = 10.0,
        transport: httpx.AsyncBaseTransport | None = None,
        app: Any | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.agent_id = agent_id
        self.service_token = service_token
        self.timeout = timeout
        self.app = app
        if app is not None:
            from starlette.testclient import TestClient

            self.transport = transport or httpx.ASGITransport(app=app)
            self._sync_client: httpx.Client | None = TestClient(app)
        else:
            self.transport = transport
            self._sync_client = None

    def _headers(self, agent_id_override: str | None = None) -> dict[str, str]:
        headers = {
            "X-Agent-ID": agent_id_override or self.agent_id,
            "Content-Type": "application/json",
        }
        if self.service_token:
            headers["X-Service-Token"] = self.service_token
        return headers

    async def acreate_run(self, board: Blackboard) -> Blackboard:
        async with httpx.AsyncClient(
            base_url=self.base_url, timeout=self.timeout, transport=self.transport
        ) as client:
            resp = await client.post(
                "/runs",
                content=board.model_dump_json(),
                headers=self._headers(),
            )
            resp.raise_for_status()
            return Blackboard.model_validate(resp.json())

    async def aget_run(self, run_id: str, agent_id: str | None = None) -> Blackboard:
        async with httpx.AsyncClient(
            base_url=self.base_url, timeout=self.timeout, transport=self.transport
        ) as client:
            resp = await client.get(
                f"/runs/{run_id}",
                headers=self._headers(agent_id),
            )
            resp.raise_for_status()
            return Blackboard.model_validate(resp.json())

    async def aget_zone(
        self, run_id: str, zone: str, agent_id: str | None = None
    ) -> Any:
        async with httpx.AsyncClient(
            base_url=self.base_url, timeout=self.timeout, transport=self.transport
        ) as client:
            resp = await client.get(
                f"/runs/{run_id}/zones/{zone}",
                headers=self._headers(agent_id),
            )
            resp.raise_for_status()
            return resp.json()

    async def aappend_event(
        self,
        run_id: str,
        zone: str,
        payload: dict[str, Any],
        expected_version: int,
        op: str = "update",
        agent_id: str | None = None,
    ) -> dict[str, Any]:
        async with httpx.AsyncClient(
            base_url=self.base_url, timeout=self.timeout, transport=self.transport
        ) as client:
            resp = await client.post(
                f"/runs/{run_id}/events",
                json={
                    "agent_id": agent_id or self.agent_id,
                    "zone": zone,
                    "op": op,
                    "payload": payload,
                    "expected_version": expected_version,
                },
                headers=self._headers(agent_id),
            )
            resp.raise_for_status()
            return resp.json()

    async def aget_events(self, run_id: str) -> list[dict[str, Any]]:
        async with httpx.AsyncClient(
            base_url=self.base_url, timeout=self.timeout, transport=self.transport
        ) as client:
            resp = await client.get(
                f"/runs/{run_id}/events",
                headers=self._headers(),
            )
            resp.raise_for_status()
            return resp.json()

    # Synchronous helper methods
    def create_run(self, board: Blackboard) -> Blackboard:
        if self._sync_client:
            resp = self._sync_client.post(
                "/runs",
                content=board.model_dump_json(),
                headers=self._headers(),
            )
            resp.raise_for_status()
            return Blackboard.model_validate(resp.json())
        with httpx.Client(
            base_url=self.base_url, timeout=self.timeout
        ) as client:
            resp = client.post(
                "/runs",
                content=board.model_dump_json(),
                headers=self._headers(),
            )
            resp.raise_for_status()
            return Blackboard.model_validate(resp.json())

    def get_run(self, run_id: str, agent_id: str | None = None) -> Blackboard:
        if self._sync_client:
            resp = self._sync_client.get(
                f"/runs/{run_id}",
                headers=self._headers(agent_id),
            )
            resp.raise_for_status()
            return Blackboard.model_validate(resp.json())
        with httpx.Client(
            base_url=self.base_url, timeout=self.timeout
        ) as client:
            resp = client.get(
                f"/runs/{run_id}",
                headers=self._headers(agent_id),
            )
            resp.raise_for_status()
            return Blackboard.model_validate(resp.json())

    def get_zone(self, run_id: str, zone: str, agent_id: str | None = None) -> Any:
        if self._sync_client:
            resp = self._sync_client.get(
                f"/runs/{run_id}/zones/{zone}",
                headers=self._headers(agent_id),
            )
            resp.raise_for_status()
            return resp.json()
        with httpx.Client(
            base_url=self.base_url, timeout=self.timeout
        ) as client:
            resp = client.get(
                f"/runs/{run_id}/zones/{zone}",
                headers=self._headers(agent_id),
            )
            resp.raise_for_status()
            return resp.json()

    def append_event(
        self,
        run_id: str,
        zone: str,
        payload: dict[str, Any],
        expected_version: int,
        op: str = "update",
        agent_id: str | None = None,
    ) -> dict[str, Any]:
        if self._sync_client:
            resp = self._sync_client.post(
                f"/runs/{run_id}/events",
                json={
                    "agent_id": agent_id or self.agent_id,
                    "zone": zone,
                    "op": op,
                    "payload": payload,
                    "expected_version": expected_version,
                },
                headers=self._headers(agent_id),
            )
            resp.raise_for_status()
            return resp.json()
        with httpx.Client(
            base_url=self.base_url, timeout=self.timeout
        ) as client:
            resp = client.post(
                f"/runs/{run_id}/events",
                json={
                    "agent_id": agent_id or self.agent_id,
                    "zone": zone,
                    "op": op,
                    "payload": payload,
                    "expected_version": expected_version,
                },
                headers=self._headers(agent_id),
            )
            resp.raise_for_status()
            return resp.json()

    def append_event_with_retry(
        self,
        run_id: str,
        zone: str,
        payload: dict[str, Any],
        expected_version: int,
        op: str = "update",
        agent_id: str | None = None,
        max_retries: int = 5,
    ) -> tuple[dict[str, Any], int]:
        """Append event with automatic retry on HTTP 409 version mismatch."""
        import time

        ver = expected_version
        for attempt in range(max_retries):
            try:
                res = self.append_event(
                    run_id=run_id,
                    zone=zone,
                    payload=payload,
                    expected_version=ver,
                    op=op,
                    agent_id=agent_id,
                )
                return res, ver + 1
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 409 and attempt < max_retries - 1:
                    time.sleep(0.01 * (attempt + 1))
                    latest = self.get_run(run_id, agent_id=agent_id)
                    ver = latest.version
                    continue
                raise

    def get_events(self, run_id: str) -> list[dict[str, Any]]:
        if self._sync_client:
            resp = self._sync_client.get(
                f"/runs/{run_id}/events",
                headers=self._headers(),
            )
            resp.raise_for_status()
            return resp.json()
        with httpx.Client(
            base_url=self.base_url, timeout=self.timeout
        ) as client:
            resp = client.get(
                f"/runs/{run_id}/events",
                headers=self._headers(),
            )
            resp.raise_for_status()
            return resp.json()
