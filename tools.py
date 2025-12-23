"""
Tool definitions using LangChain's @tool decorator with Pydantic schemas.

Tools are divided into:
- READ tools: Execute immediately, return data
- PROPOSAL tools: Return proposal for user confirmation, don't execute
"""

import logging
from typing import Optional
from langchain_core.tools import tool

import google_api
from schemas import (
    GetCalendarEventsArgs,
    ProposeCreateTaskArgs,
    ProposeEditTaskArgs,
    ProposeDeleteTaskArgs,
    ProposeCompleteTaskArgs,
    ProposeCreateEventArgs,
    ProposeEditEventArgs,
    ProposeDeleteEventArgs,
)

logger = logging.getLogger(__name__)


# ============================================================
# READ TOOLS (execute immediately)
# ============================================================

@tool(args_schema=GetCalendarEventsArgs)
def get_calendar_events(days_ahead: int = 7) -> list:
    """Get calendar events for the next N days. Use when user asks about their schedule, upcoming events, or what they have planned."""
    logger.info(f"Getting calendar events for next {days_ahead} days")
    return google_api.get_events(days_ahead=days_ahead)


@tool
def get_today_events() -> list:
    """Get calendar events for today only. Use when user asks specifically about today's schedule."""
    logger.info("Getting today's events")
    return google_api.get_today_events()


@tool
def get_tasks() -> list:
    """Get all incomplete tasks. Use when user asks about their tasks, todos, or what they need to do."""
    logger.info("Getting tasks")
    return google_api.get_tasks()


# ============================================================
# PROPOSAL TOOLS - Tasks (return proposal, don't execute)
# ============================================================

@tool(args_schema=ProposeCreateTaskArgs)
def propose_create_task(title: str, notes: str = "", due_date: Optional[str] = None) -> dict:
    """Propose creating a new task. User will be asked to confirm before it's created. Use this when user wants to add a new task or todo."""
    logger.info(f"Proposing to create task: {title}")
    return {
        "proposal_type": "create_task",
        "title": title,
        "notes": notes,
        "due_date": due_date,
    }


@tool(args_schema=ProposeEditTaskArgs)
def propose_edit_task(
    task_id: str,
    current_title: str,
    tasklist_id: Optional[str] = None,
    title: Optional[str] = None,
    notes: Optional[str] = None,
    due_date: Optional[str] = None
) -> dict:
    """Propose editing an existing task. User will confirm before changes are made. Use get_tasks first to find the task_id."""
    logger.info(f"Proposing to edit task: {current_title}")
    return {
        "proposal_type": "edit_task",
        "task_id": task_id,
        "current_title": current_title,
        "tasklist_id": tasklist_id,
        "new_title": title,
        "new_notes": notes,
        "new_due_date": due_date,
    }


@tool(args_schema=ProposeDeleteTaskArgs)
def propose_delete_task(task_id: str, task_title: str, tasklist_id: Optional[str] = None) -> dict:
    """Propose deleting a task. User will confirm before deletion. Use get_tasks first to find the task_id."""
    logger.info(f"Proposing to delete task: {task_title}")
    return {
        "proposal_type": "delete_task",
        "task_id": task_id,
        "task_title": task_title,
        "tasklist_id": tasklist_id,
    }


@tool(args_schema=ProposeCompleteTaskArgs)
def propose_complete_task(task_id: str, task_title: str, tasklist_id: Optional[str] = None) -> dict:
    """Propose marking a task as complete. User will confirm before completion. Use get_tasks first to find the task_id."""
    logger.info(f"Proposing to complete task: {task_title}")
    return {
        "proposal_type": "complete_task",
        "task_id": task_id,
        "task_title": task_title,
        "tasklist_id": tasklist_id,
    }


# ============================================================
# PROPOSAL TOOLS - Calendar Events (return proposal, don't execute)
# ============================================================

@tool(args_schema=ProposeCreateEventArgs)
def propose_create_event(
    title: str,
    date: str,
    time: Optional[str] = None,
    duration_hours: int = 1,
    location: str = "",
    description: str = ""
) -> dict:
    """Propose creating a new calendar event. User will confirm before creation. Use for scheduling meetings, appointments, reminders."""
    logger.info(f"Proposing to create event: {title} on {date}")
    return {
        "proposal_type": "create_event",
        "title": title,
        "date": date,
        "time": time,
        "duration_hours": duration_hours,
        "location": location,
        "description": description,
    }


@tool(args_schema=ProposeEditEventArgs)
def propose_edit_event(
    event_id: str,
    current_title: str,
    current_datetime: Optional[str] = None,
    title: Optional[str] = None,
    date: Optional[str] = None,
    time: Optional[str] = None,
    location: Optional[str] = None,
    description: Optional[str] = None
) -> dict:
    """Propose editing an existing calendar event. User will confirm before changes. Use get_calendar_events first to find event_id."""
    logger.info(f"Proposing to edit event: {current_title}")
    return {
        "proposal_type": "edit_event",
        "event_id": event_id,
        "current_title": current_title,
        "current_datetime": current_datetime,
        "new_title": title,
        "new_date": date,
        "new_time": time,
        "new_location": location,
        "new_description": description,
    }


@tool(args_schema=ProposeDeleteEventArgs)
def propose_delete_event(event_id: str, event_title: str, event_datetime: Optional[str] = None) -> dict:
    """Propose deleting a calendar event. User will confirm before deletion. Use get_calendar_events first to find event_id."""
    logger.info(f"Proposing to delete event: {event_title}")
    return {
        "proposal_type": "delete_event",
        "event_id": event_id,
        "event_title": event_title,
        "event_datetime": event_datetime,
    }


# ============================================================
# TOOL LISTS
# ============================================================

# Read tools - execute immediately
READ_TOOLS = [
    get_calendar_events,
    get_today_events,
    get_tasks,
]

# Proposal tools - need user confirmation
PROPOSAL_TOOLS = [
    propose_create_task,
    propose_edit_task,
    propose_delete_task,
    propose_complete_task,
    propose_create_event,
    propose_edit_event,
    propose_delete_event,
]

# All tools combined
ALL_TOOLS = READ_TOOLS + PROPOSAL_TOOLS

# Tool name to function mapping (for execution after confirmation)
PROPOSAL_TOOL_NAMES = {t.name for t in PROPOSAL_TOOLS}


# ============================================================
# EXECUTION (called after user confirms a proposal)
# ============================================================

def execute_confirmed_proposal(proposal: dict) -> dict:
    """
    Execute a confirmed proposal.
    Called when user clicks 'Confirm' on a proposal.

    Args:
        proposal: The proposal dict returned by a propose_* tool

    Returns:
        Result from the actual operation
    """
    proposal_type = proposal.get("proposal_type")
    logger.info(f"Executing confirmed proposal: {proposal_type}")

    try:
        if proposal_type == "create_task":
            return google_api.create_task(
                title=proposal["title"],
                notes=proposal.get("notes", ""),
                due_date=proposal.get("due_date"),
            )

        elif proposal_type == "edit_task":
            return google_api.edit_task(
                task_id=proposal["task_id"],
                tasklist_id=proposal.get("tasklist_id"),
                title=proposal.get("new_title"),
                notes=proposal.get("new_notes"),
                due_date=proposal.get("new_due_date"),
            )

        elif proposal_type == "delete_task":
            return google_api.delete_task(
                task_id=proposal["task_id"],
                tasklist_id=proposal.get("tasklist_id"),
            )

        elif proposal_type == "complete_task":
            return google_api.complete_task(
                task_id=proposal["task_id"],
                tasklist_id=proposal.get("tasklist_id"),
            )

        elif proposal_type == "create_event":
            return google_api.create_event(
                title=proposal["title"],
                date=proposal["date"],
                time=proposal.get("time"),
                duration_hours=proposal.get("duration_hours", 1),
                location=proposal.get("location", ""),
                description=proposal.get("description", ""),
            )

        elif proposal_type == "edit_event":
            return google_api.edit_event(
                event_id=proposal["event_id"],
                title=proposal.get("new_title"),
                date=proposal.get("new_date"),
                time=proposal.get("new_time"),
                location=proposal.get("new_location"),
                description=proposal.get("new_description"),
            )

        elif proposal_type == "delete_event":
            return google_api.delete_event(
                event_id=proposal["event_id"],
            )

        else:
            return {"error": f"Unknown proposal type: {proposal_type}"}

    except Exception as e:
        logger.exception(f"Error executing proposal: {e}")
        return {"error": str(e)}
