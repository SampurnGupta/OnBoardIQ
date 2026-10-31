"""Messaging strategy interface and implementations for OnboardIQ.

Per docs/06_IMPLEMENTATION_PLAN.md T14:
- BlackboardStrategy: hand-offs happen exclusively via the Blackboard.
- HybridP2PStrategy: upstream results are passed directly peer-to-peer to downstream
  agents, while the blackboard stores versioned state and the audit log.
- Both modes produce identical report schemas.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from onboardiq.blackboard.client import BlackboardClient
from onboardiq.schema import Mode


class MessagingStrategy(ABC):
    """Abstract messaging strategy interface."""

    def __init__(self, mode: Mode):
        self.mode = mode

    @abstractmethod
    def handoff(
        self,
        sender_agent_id: str,
        receiver_agent_id: str,
        zone: str,
        payload: dict[str, Any],
        run_id: str,
        board_client: BlackboardClient,
        current_version: int,
        op: str = "update",
    ) -> tuple[dict[str, Any], int]:
        """Deliver data from sender to receiver and persist state to Blackboard."""

    @abstractmethod
    def retrieve(
        self,
        receiver_agent_id: str,
        zone: str,
        run_id: str,
        board_client: BlackboardClient,
        direct_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Retrieve data for the receiving agent."""


class BlackboardStrategy(MessagingStrategy):
    """Pure blackboard strategy: hand-offs only via the shared board."""

    def __init__(self):
        super().__init__(mode=Mode.BLACKBOARD)

    def handoff(
        self,
        sender_agent_id: str,
        receiver_agent_id: str,
        zone: str,
        payload: dict[str, Any],
        run_id: str,
        board_client: BlackboardClient,
        current_version: int,
        op: str = "update",
    ) -> tuple[dict[str, Any], int]:
        # Writes payload to the blackboard zone
        _, new_ver = board_client.append_event_with_retry(
            run_id=run_id,
            zone=zone,
            payload=payload,
            expected_version=current_version,
            op=op,
            agent_id=sender_agent_id,
        )
        # In pure blackboard mode, downstream agent must read from board; no direct in-memory payload passed
        return {}, new_ver

    def retrieve(
        self,
        receiver_agent_id: str,
        zone: str,
        run_id: str,
        board_client: BlackboardClient,
        direct_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        # Always reads from the blackboard zone
        data = board_client.get_zone(run_id=run_id, zone=zone, agent_id=receiver_agent_id)
        return data if isinstance(data, dict) else {}


class HybridP2PStrategy(MessagingStrategy):
    """Hybrid P2P strategy: direct agent hand-offs with background blackboard logging."""

    def __init__(self):
        super().__init__(mode=Mode.HYBRID_P2P)

    def handoff(
        self,
        sender_agent_id: str,
        receiver_agent_id: str,
        zone: str,
        payload: dict[str, Any],
        run_id: str,
        board_client: BlackboardClient,
        current_version: int,
        op: str = "update",
    ) -> tuple[dict[str, Any], int]:
        # Persist to blackboard for compliance audit log
        _, new_ver = board_client.append_event_with_retry(
            run_id=run_id,
            zone=zone,
            payload=payload,
            expected_version=current_version,
            op=op,
            agent_id=sender_agent_id,
        )
        # Return the payload directly for peer-to-peer in-memory handoff
        return payload, new_ver

    def retrieve(
        self,
        receiver_agent_id: str,
        zone: str,
        run_id: str,
        board_client: BlackboardClient,
        direct_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        # If upstream directly handed off the payload, use it immediately
        if direct_payload is not None and bool(direct_payload):
            return direct_payload
        # Fall back to reading from blackboard if direct payload was not available
        data = board_client.get_zone(run_id=run_id, zone=zone, agent_id=receiver_agent_id)
        return data if isinstance(data, dict) else {}


def get_messaging_strategy(mode: Mode | str) -> MessagingStrategy:
    """Factory function for messaging strategy."""
    mode_str = mode.value if isinstance(mode, Mode) else str(mode)
    if mode_str == Mode.HYBRID_P2P.value:
        return HybridP2PStrategy()
    return BlackboardStrategy()
