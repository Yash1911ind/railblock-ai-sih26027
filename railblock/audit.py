"""Lightweight, session-scoped audit trail.

This is a prototype audit log for demonstration purposes only — it is NOT a
regulatory-compliant audit system and makes no such claim. Events are plain
dicts kept in whatever list the caller owns (typically
`st.session_state.audit_log`); this module only provides pure helpers so the
format stays consistent everywhere it's recorded or displayed.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

AUDIT_ACTIONS = (
    "AI Recommendation Generated",
    "AI Recommendation Approved",
    "AI Recommendation Rejected",
    "Schedule Generated",
    "Schedule Modified",
    "Simulation Executed",
    "Disruption Introduced",
    "Re-plan Generated",
    "Coordination Approved",
    "Coordination Rejected",
    "Demo Reset",
)


def record_event(log: list[dict[str, Any]], action: str, entity: str, reason: str) -> dict[str, Any]:
    """Append one event to `log` (in place) and return it.

    `log` is owned by the caller — this function does not persist anything
    itself; it exists purely to keep the event shape (timestamp, action,
    entity, reason) consistent wherever an event is recorded.
    """
    event = {
        "timestamp": datetime.now().strftime("%H:%M:%S"),
        "action": action,
        "entity": entity,
        "reason": reason,
    }
    log.append(event)
    return event


def format_event(event: dict[str, Any]) -> str:
    return f"{event['timestamp']} — {event['action']} — {event['entity']} — {event['reason']}"
