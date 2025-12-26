"""
Session state management for the Personal Assistant Agent.

Tracks:
- Which event/task IDs the LLM has seen (from READ tool results)
- When data was last fetched (freshness)

Used to validate proposals before execution - prevents:
- Invented IDs (editing non-existent events/tasks)
- Stale data (acting on outdated information)
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional
import logging

logger = logging.getLogger(__name__)

# How long fetched data is considered "fresh"
FRESHNESS_TTL = timedelta(minutes=2)


@dataclass
class SessionState:
    """Per-user session state tracking what data has been fetched"""

    # Allowed IDs (populated from READ tool results)
    allowed_event_ids: set[str] = field(default_factory=set)
    allowed_task_ids: set[str] = field(default_factory=set)

    # Freshness timestamps
    calendar_fetched_at: Optional[datetime] = None
    tasks_fetched_at: Optional[datetime] = None

    def is_calendar_fresh(self) -> bool:
        """Check if calendar data is still fresh"""
        if not self.calendar_fetched_at:
            return False
        return datetime.now() - self.calendar_fetched_at < FRESHNESS_TTL

    def is_tasks_fresh(self) -> bool:
        """Check if tasks data is still fresh"""
        if not self.tasks_fetched_at:
            return False
        return datetime.now() - self.tasks_fetched_at < FRESHNESS_TTL

    def update_from_calendar_read(self, events: list):
        """
        Update state after get_calendar_events/get_today_events.
        Extracts event IDs from the result and marks calendar as fresh.
        """
        self.allowed_event_ids = {e['id'] for e in events if e.get('id')}
        self.calendar_fetched_at = datetime.now()
        logger.debug(f"Session updated: {len(self.allowed_event_ids)} event IDs cached")

    def update_from_tasks_read(self, tasks: list):
        """
        Update state after get_tasks.
        Extracts task IDs from the result and marks tasks as fresh.
        """
        self.allowed_task_ids = {t['id'] for t in tasks if t.get('id')}
        self.tasks_fetched_at = datetime.now()
        logger.debug(f"Session updated: {len(self.allowed_task_ids)} task IDs cached")

    def validate_event_proposal(self, event_id: str) -> tuple[bool, str]:
        """
        Validate event ID for edit/delete proposals.

        Returns:
            (is_valid, error_message)
        """
        if not self.is_calendar_fresh():
            return False, "Calendar data is stale. Call get_calendar_events first to get current data."

        if event_id not in self.allowed_event_ids:
            return False, f"Event ID '{event_id}' not found in recent calendar fetch. Call get_calendar_events first."

        return True, ""

    def validate_task_proposal(self, task_id: str) -> tuple[bool, str]:
        """
        Validate task ID for edit/delete/complete proposals.

        Returns:
            (is_valid, error_message)
        """
        if not self.is_tasks_fresh():
            return False, "Task data is stale. Call get_tasks first to get current data."

        if task_id not in self.allowed_task_ids:
            return False, f"Task ID '{task_id}' not found in recent tasks fetch. Call get_tasks first."

        return True, ""

    def clear(self):
        """Reset session state (e.g., on /start)"""
        self.allowed_event_ids.clear()
        self.allowed_task_ids.clear()
        self.calendar_fetched_at = None
        self.tasks_fetched_at = None
        logger.debug("Session cleared")


# ============================================================
# PER-USER SESSION STORAGE
# ============================================================

sessions: dict[int, SessionState] = {}


def get_session(user_id: int) -> SessionState:
    """Get or create session state for a user"""
    if user_id not in sessions:
        sessions[user_id] = SessionState()
    return sessions[user_id]


def clear_session(user_id: int):
    """Clear session state for a user"""
    if user_id in sessions:
        sessions[user_id].clear()
    else:
        sessions[user_id] = SessionState()
