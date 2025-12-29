"""
Proactive notification logic.

Contains job callbacks for scheduled notifications and message builders.
Uses hybrid approach: templates for structure, optional LLM for personalization.
"""

import logging
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Optional

from telegram.ext import ContextTypes

import database
import google_api
import llm_handler
from langchain_core.messages import HumanMessage
from config import DEFAULT_TIMEZONE, EVENT_REMINDER_MINUTES

logger = logging.getLogger(__name__)


# ============================================================
# MESSAGE TEMPLATES (HTML format)
# ============================================================

BRIEFING_TEMPLATE = """<b>Good morning!</b>

<b>Today's Events ({event_count}):</b>
{events_section}

<b>Pending Tasks ({task_count}):</b>
{tasks_section}
{llm_commentary}"""

BRIEFING_NO_EVENTS = "No events scheduled for today."
BRIEFING_NO_TASKS = "No pending tasks."

EVENT_REMINDER_TEMPLATE = """<b>Reminder:</b> {title}
Starts in ~{minutes} minutes ({time}){location_line}"""

OVERDUE_NUDGE_TEMPLATE = """<b>Task Reminder</b>

You have {overdue_count} overdue task(s):
{tasks_list}"""


# ============================================================
# MESSAGE BUILDERS
# ============================================================

def format_event_for_briefing(event: dict) -> str:
    """Format a single event for the briefing list."""
    title = event.get('summary', 'Untitled')
    start = event.get('start', '')

    # Extract time from start string (e.g., "2025-12-26 10:00-11:00" -> "10:00")
    time_part = ""
    if ' ' in start:
        time_part = start.split(' ')[1].split('-')[0]  # Get start time

    location = event.get('location', '')
    loc_str = f" @ {location}" if location else ""

    if time_part:
        return f"  {time_part} - {title}{loc_str}"
    else:
        return f"  (All day) {title}{loc_str}"


def format_task_for_list(task: dict) -> str:
    """Format a single task for display."""
    title = task.get('title', 'Untitled')
    due = task.get('due', '')

    if due:
        # Parse due date and format nicely
        try:
            due_date = datetime.fromisoformat(due.replace('Z', '+00:00'))
            due_str = due_date.strftime('%b %d')
            return f"  - {title} (due {due_str})"
        except (ValueError, AttributeError):
            return f"  - {title}"
    return f"  - {title}"


def build_briefing_message(
    events: list,
    tasks: list,
    use_llm: bool = True
) -> str:
    """
    Build daily briefing message.

    Args:
        events: Today's calendar events
        tasks: Pending tasks
        use_llm: Whether to add LLM commentary
    """
    # Format events
    if events:
        events_section = "\n".join(format_event_for_briefing(e) for e in events)
    else:
        events_section = BRIEFING_NO_EVENTS

    # Format tasks (show first 5 to keep message manageable)
    if tasks:
        task_lines = [format_task_for_list(t) for t in tasks[:5]]
        if len(tasks) > 5:
            task_lines.append(f"  ... and {len(tasks) - 5} more")
        tasks_section = "\n".join(task_lines)
    else:
        tasks_section = BRIEFING_NO_TASKS

    # Get LLM commentary if enabled and there's content to comment on
    llm_commentary = ""
    if use_llm and (events or tasks):
        try:
            commentary = generate_briefing_commentary(events, tasks)
            if commentary:
                llm_commentary = f"\n{commentary}"
        except Exception as e:
            logger.warning(f"Failed to generate LLM commentary: {e}")
            # Fall back to no commentary

    return BRIEFING_TEMPLATE.format(
        event_count=len(events),
        events_section=events_section,
        task_count=len(tasks),
        tasks_section=tasks_section,
        llm_commentary=llm_commentary
    )


def build_event_reminder(event: dict, minutes_until: int = 30) -> str:
    """Build reminder message for an upcoming event."""
    title = event.get('summary', 'Untitled')
    start = event.get('start', '')

    # Extract time
    time_part = ""
    if ' ' in start:
        time_part = start.split(' ')[1].split('-')[0]

    location = event.get('location', '')
    location_line = f"\nLocation: {location}" if location else ""

    return EVENT_REMINDER_TEMPLATE.format(
        title=title,
        minutes=minutes_until,
        time=time_part or start,
        location_line=location_line
    )


def build_overdue_nudge(tasks: list) -> str:
    """Build nudge message for overdue tasks."""
    if not tasks:
        return ""

    task_lines = [f"  - {t.get('title', 'Untitled')}" for t in tasks[:5]]
    if len(tasks) > 5:
        task_lines.append(f"  ... and {len(tasks) - 5} more")

    return OVERDUE_NUDGE_TEMPLATE.format(
        overdue_count=len(tasks),
        tasks_list="\n".join(task_lines)
    )


# ============================================================
# LLM INTEGRATION
# ============================================================

def generate_briefing_commentary(events: list, tasks: list) -> str:
    """
    Generate personalized commentary for daily briefing using LLM.
    Keeps it brief (1-2 sentences).
    """
    # Build a focused prompt
    event_summary = ", ".join(e.get('summary', 'event') for e in events[:3])
    task_summary = ", ".join(t.get('title', 'task') for t in tasks[:3])

    prompt = f"""Based on today's schedule:
Events: {event_summary or 'none'}
Tasks: {task_summary or 'none'}

Write 1-2 sentences of brief, helpful commentary (priorities, time management tips, or encouragement).
Be conversational and friendly. No emojis. Keep it under 50 words."""

    try:
        response = llm_handler.chat([HumanMessage(content=prompt)], tools=None)
        if response.content:
            return response.content.strip()
    except Exception as e:
        logger.warning(f"LLM commentary generation failed: {e}")

    return ""


# ============================================================
# JOB CALLBACKS
# ============================================================

async def daily_briefing_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Send daily briefing to a user.
    Called by job_queue at user's configured briefing time.
    """
    job = context.job
    user_id = job.chat_id

    logger.info(f"Running daily briefing for user {user_id}")

    try:
        # Check if already sent today
        today = datetime.now(ZoneInfo(DEFAULT_TIMEZONE)).strftime('%Y-%m-%d')
        if database.was_reminder_sent(user_id, 'daily_briefing', None, today):
            logger.debug(f"Briefing already sent to user {user_id} today")
            return

        # Fetch data
        events = google_api.get_today_events()
        tasks = google_api.get_tasks()

        # Build and send message
        message = build_briefing_message(events, tasks, use_llm=True)
        await context.bot.send_message(
            chat_id=user_id,
            text=message,
            parse_mode='HTML'
        )

        # Mark as sent
        database.mark_reminder_sent(user_id, 'daily_briefing', None, today)
        logger.info(f"Sent daily briefing to user {user_id}")

    except Exception as e:
        logger.error(f"Failed to send daily briefing to user {user_id}: {e}")


async def event_reminder_check_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Check for upcoming events and send reminders.
    Runs every 5 minutes, checks all users with reminders enabled.
    """
    logger.debug("Running event reminder check")

    try:
        users = database.get_all_users_with_reminders_enabled()
    except Exception as e:
        logger.error(f"Database error in event_reminder_check: {e}")
        return

    if not users:
        return

    # Get events for next hour
    try:
        events = google_api.get_events(days_ahead=1)
    except Exception as e:
        logger.error(f"Failed to fetch events for reminders: {e}")
        return

    now = datetime.now(ZoneInfo(DEFAULT_TIMEZONE))
    reminder_window_start = now + timedelta(minutes=EVENT_REMINDER_MINUTES - 2)
    reminder_window_end = now + timedelta(minutes=EVENT_REMINDER_MINUTES + 3)

    for event in events:
        # Parse event start time
        start_str = event.get('start', '')
        if not start_str or ' ' not in start_str:
            continue  # Skip all-day events

        try:
            # Parse "2025-12-26 10:00-11:00" format
            date_part, time_range = start_str.split(' ')
            start_time = time_range.split('-')[0]
            event_dt = datetime.strptime(
                f"{date_part} {start_time}",
                "%Y-%m-%d %H:%M"
            ).replace(tzinfo=ZoneInfo(DEFAULT_TIMEZONE))
        except (ValueError, IndexError):
            continue

        # Check if event starts in reminder window
        if not (reminder_window_start <= event_dt <= reminder_window_end):
            continue

        minutes_until = int((event_dt - now).total_seconds() / 60)
        event_id = event.get('id')
        today = now.strftime('%Y-%m-%d')

        # Send reminder to each eligible user
        for user in users:
            user_id = user['user_id']

            try:
                # Check if already sent
                if database.was_reminder_sent(user_id, 'event_reminder', event_id, today):
                    continue

                message = build_event_reminder(event, minutes_until)
                await context.bot.send_message(
                    chat_id=user_id,
                    text=message,
                    parse_mode='HTML'
                )

                database.mark_reminder_sent(user_id, 'event_reminder', event_id, today)
                logger.info(f"Sent event reminder to user {user_id} for '{event.get('summary')}'")

            except Exception as e:
                logger.error(f"Failed to send event reminder to user {user_id}: {e}")
                continue


async def overdue_nudge_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Check for overdue tasks and send nudges.
    Runs hourly, respects per-user nudge intervals.
    """
    logger.debug("Running overdue task nudge check")

    try:
        users = database.get_all_users_with_nudges_enabled()
    except Exception as e:
        logger.error(f"Database error in overdue_nudge_job: {e}")
        return

    if not users:
        return

    now = datetime.now(ZoneInfo(DEFAULT_TIMEZONE))
    today = now.strftime('%Y-%m-%d')

    for user in users:
        user_id = user['user_id']

        try:
            # Check if we already nudged today
            # (In future, could track last nudge time for interval-based nudging)
            if database.was_reminder_sent(user_id, 'overdue_nudge', None, today):
                continue

            # Get overdue tasks
            overdue = google_api.get_overdue_tasks()
            if not overdue:
                continue

            message = build_overdue_nudge(overdue)
            await context.bot.send_message(
                chat_id=user_id,
                text=message,
                parse_mode='HTML'
            )

            database.mark_reminder_sent(user_id, 'overdue_nudge', None, today)
            logger.info(f"Sent overdue nudge to user {user_id} ({len(overdue)} tasks)")

        except Exception as e:
            logger.error(f"Failed to send overdue nudge to user {user_id}: {e}")
            continue


# ============================================================
# UTILITY
# ============================================================

async def send_test_briefing(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> None:
    """Send a test briefing immediately (for debugging)."""
    events = google_api.get_today_events()
    tasks = google_api.get_tasks()
    message = build_briefing_message(events, tasks, use_llm=True)

    await context.bot.send_message(
        chat_id=user_id,
        text=message,
        parse_mode='HTML'
    )
