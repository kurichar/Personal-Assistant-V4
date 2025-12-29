"""
SQLite database operations for proactive features.

Handles user preferences and sent reminder tracking.
"""

import sqlite3
import logging
from datetime import datetime
from typing import Optional
from contextlib import contextmanager

from config import DATABASE_PATH

logger = logging.getLogger(__name__)


@contextmanager
def get_connection():
    """Get a database connection with proper cleanup."""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row  # Return dicts instead of tuples
    try:
        yield conn
    finally:
        conn.close()


def init_db() -> None:
    """Initialize database tables if they don't exist."""
    with get_connection() as conn:
        cursor = conn.cursor()

        # User preferences table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                timezone TEXT DEFAULT 'Asia/Jerusalem',
                briefing_enabled INTEGER DEFAULT 0,
                briefing_time TEXT DEFAULT '08:00',
                reminders_enabled INTEGER DEFAULT 1,
                nudges_enabled INTEGER DEFAULT 1,
                nudge_interval_hours INTEGER DEFAULT 4,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Sent reminders tracking table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sent_reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                reminder_type TEXT NOT NULL,
                reference_id TEXT,
                reference_date TEXT,
                sent_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id),
                UNIQUE(user_id, reminder_type, reference_id, reference_date)
            )
        """)

        # Index for efficient lookups
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_sent_reminders_lookup
            ON sent_reminders(user_id, reminder_type, reference_id, reference_date)
        """)

        conn.commit()
        logger.info("Database initialized")


def get_user(user_id: int) -> Optional[dict]:
    """Get user preferences by user_id."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def create_user(user_id: int, timezone: str = 'Asia/Jerusalem') -> dict:
    """Create a new user with default preferences."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR IGNORE INTO users (user_id, timezone)
            VALUES (?, ?)
        """, (user_id, timezone))
        conn.commit()

    return get_user(user_id)


def update_user(user_id: int, **kwargs) -> Optional[dict]:
    """
    Update user preferences.

    Allowed fields: timezone, briefing_enabled, briefing_time,
                   reminders_enabled, nudges_enabled, nudge_interval_hours
    """
    allowed_fields = {
        'timezone', 'briefing_enabled', 'briefing_time',
        'reminders_enabled', 'nudges_enabled', 'nudge_interval_hours'
    }

    # Filter to allowed fields only
    updates = {k: v for k, v in kwargs.items() if k in allowed_fields}
    if not updates:
        return get_user(user_id)

    # Build SET clause
    set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
    values = list(updates.values()) + [user_id]

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(f"""
            UPDATE users
            SET {set_clause}, updated_at = CURRENT_TIMESTAMP
            WHERE user_id = ?
        """, values)
        conn.commit()

    return get_user(user_id)


def was_reminder_sent(
    user_id: int,
    reminder_type: str,
    reference_id: Optional[str],
    reference_date: str
) -> bool:
    """Check if a specific reminder was already sent."""
    with get_connection() as conn:
        cursor = conn.cursor()

        if reference_id is None:
            cursor.execute("""
                SELECT 1 FROM sent_reminders
                WHERE user_id = ? AND reminder_type = ?
                AND reference_id IS NULL AND reference_date = ?
            """, (user_id, reminder_type, reference_date))
        else:
            cursor.execute("""
                SELECT 1 FROM sent_reminders
                WHERE user_id = ? AND reminder_type = ?
                AND reference_id = ? AND reference_date = ?
            """, (user_id, reminder_type, reference_id, reference_date))

        return cursor.fetchone() is not None


def mark_reminder_sent(
    user_id: int,
    reminder_type: str,
    reference_id: Optional[str],
    reference_date: str
) -> None:
    """Mark a reminder as sent to prevent duplicates."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR IGNORE INTO sent_reminders
            (user_id, reminder_type, reference_id, reference_date)
            VALUES (?, ?, ?, ?)
        """, (user_id, reminder_type, reference_id, reference_date))
        conn.commit()


def get_all_users_with_briefings() -> list[dict]:
    """Get all users who have briefings enabled."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM users WHERE briefing_enabled = 1
        """)
        return [dict(row) for row in cursor.fetchall()]


def get_all_users_with_reminders_enabled() -> list[dict]:
    """Get all users who have event reminders enabled."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM users WHERE reminders_enabled = 1
        """)
        return [dict(row) for row in cursor.fetchall()]


def get_all_users_with_nudges_enabled() -> list[dict]:
    """Get all users who have task nudges enabled."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM users WHERE nudges_enabled = 1
        """)
        return [dict(row) for row in cursor.fetchall()]


def cleanup_old_reminders(days_to_keep: int = 7) -> int:
    """
    Clean up old sent_reminders entries to prevent table bloat.
    Returns number of deleted rows.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            DELETE FROM sent_reminders
            WHERE sent_at < datetime('now', ?)
        """, (f'-{days_to_keep} days',))
        deleted = cursor.rowcount
        conn.commit()

        if deleted > 0:
            logger.info(f"Cleaned up {deleted} old reminder records")

        return deleted
