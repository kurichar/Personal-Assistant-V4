"""
Job scheduler setup for proactive notifications.

Handles initialization and configuration of scheduled jobs.
"""

import logging
from datetime import time
from zoneinfo import ZoneInfo

from telegram.ext import Application

import database
from proactive import (
    daily_briefing_job,
    event_reminder_check_job,
    overdue_nudge_job,
)
from config import DEFAULT_TIMEZONE, OVERDUE_CHECK_INTERVAL_MINUTES

logger = logging.getLogger(__name__)


def setup_scheduled_jobs(application: Application) -> None:
    """
    Set up all scheduled jobs for the application.

    Should be called once during bot startup, after database is initialized.
    """
    job_queue = application.job_queue

    # Event reminder check - runs every 5 minutes
    job_queue.run_repeating(
        event_reminder_check_job,
        interval=300,  # 5 minutes
        first=10,      # Start 10 seconds after bot launch
        name="event_reminder_check"
    )
    logger.info("Scheduled event reminder check (every 5 min)")

    # Overdue task nudge - runs hourly (configurable)
    job_queue.run_repeating(
        overdue_nudge_job,
        interval=OVERDUE_CHECK_INTERVAL_MINUTES * 60,
        first=60,  # Start 1 minute after bot launch
        name="overdue_nudge_check"
    )
    logger.info(f"Scheduled overdue task nudge (every {OVERDUE_CHECK_INTERVAL_MINUTES} min)")

    # Schedule daily briefings for all users who have them enabled
    schedule_all_user_briefings(application)

    # Optional: Clean up old reminder records once a day
    job_queue.run_daily(
        cleanup_job,
        time=time(hour=3, minute=0, tzinfo=ZoneInfo(DEFAULT_TIMEZONE)),
        name="cleanup_old_reminders"
    )
    logger.info("Scheduled daily cleanup job (3 AM)")


def schedule_all_user_briefings(application: Application) -> None:
    """
    Schedule daily briefings for all users who have them enabled.
    Called on startup and when a user enables/changes their briefing time.
    """
    try:
        users = database.get_all_users_with_briefings()
    except Exception as e:
        logger.error(f"Failed to get users for briefing scheduling: {e}")
        return

    for user in users:
        schedule_user_briefing(
            application,
            user['user_id'],
            user['briefing_time'],
            user.get('timezone', DEFAULT_TIMEZONE)
        )


def schedule_user_briefing(
    application: Application,
    user_id: int,
    briefing_time: str,
    timezone: str = DEFAULT_TIMEZONE
) -> None:
    """
    Schedule or reschedule daily briefing for a specific user.

    Args:
        application: Telegram Application instance
        user_id: Telegram user ID
        briefing_time: Time in HH:MM format (24-hour)
        timezone: User's timezone
    """
    job_queue = application.job_queue
    job_name = f"briefing_{user_id}"

    # Remove existing job for this user if any
    current_jobs = job_queue.get_jobs_by_name(job_name)
    for job in current_jobs:
        job.schedule_removal()
        logger.debug(f"Removed existing briefing job for user {user_id}")

    try:
        hour, minute = map(int, briefing_time.split(':'))
        tz = ZoneInfo(timezone)
        briefing_time_obj = time(hour=hour, minute=minute, tzinfo=tz)

        job_queue.run_daily(
            daily_briefing_job,
            time=briefing_time_obj,
            chat_id=user_id,
            name=job_name
        )
        logger.info(f"Scheduled briefing for user {user_id} at {briefing_time} ({timezone})")

    except Exception as e:
        logger.error(f"Failed to schedule briefing for user {user_id}: {e}")


def remove_user_briefing(application: Application, user_id: int) -> None:
    """
    Remove the scheduled daily briefing for a user.

    Called when user disables their briefing.
    """
    job_queue = application.job_queue
    job_name = f"briefing_{user_id}"

    current_jobs = job_queue.get_jobs_by_name(job_name)
    for job in current_jobs:
        job.schedule_removal()

    logger.info(f"Removed briefing job for user {user_id}")


async def cleanup_job(context) -> None:
    """Clean up old reminder records from database."""
    try:
        deleted = database.cleanup_old_reminders(days_to_keep=7)
        if deleted > 0:
            logger.info(f"Cleanup job: removed {deleted} old reminder records")
    except Exception as e:
        logger.error(f"Cleanup job failed: {e}")
