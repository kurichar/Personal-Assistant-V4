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
    tasklist_id: str,
    title: Optional[str] = None,
    notes: Optional[str] = None,
    due_date: Optional[str] = None
) -> dict:
    """Propose editing an existing task. Call get_tasks first to get task_id, current_title, and tasklist_id."""
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
def propose_delete_task(task_id: str, task_title: str, tasklist_id: str) -> dict:
    """Propose deleting a task. Call get_tasks first to get task_id, task_title, and tasklist_id."""
    logger.info(f"Proposing to delete task: {task_title}")
    return {
        "proposal_type": "delete_task",
        "task_id": task_id,
        "task_title": task_title,
        "tasklist_id": tasklist_id,
    }


@tool(args_schema=ProposeCompleteTaskArgs)
def propose_complete_task(task_id: str, task_title: str, tasklist_id: str) -> dict:
    """Propose marking a task as complete. Call get_tasks first to get task_id, task_title, and tasklist_id."""
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
    duration_minutes: int = 60,
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
        "duration_minutes": duration_minutes,
        "location": location,
        "description": description,
    }


@tool(args_schema=ProposeEditEventArgs)
def propose_edit_event(
    event_id: str,
    current_title: str,
    current_datetime: str,
    new_title: Optional[str] = None,
    new_date: Optional[str] = None,
    new_start_time: Optional[str] = None,
    new_end_time: Optional[str] = None,
    new_description: Optional[str] = None,
    new_location: Optional[str] = None
) -> dict:
    """
    Propose editing an existing calendar event.

    IMPORTANT: Call get_calendar_events first to get event_id, current_title, and current_datetime.
    When changing time, provide BOTH new_start_time AND new_end_time.
    """
    logger.info(f"Proposing to edit event: {current_title}")

    # Pure function - just return the proposal, no API calls
    # LLM must provide current_* fields from get_calendar_events results
    return {
        "proposal_type": "edit_event",
        "event_id": event_id,
        "current_title": current_title,
        "current_datetime": current_datetime,
        "new_title": new_title,
        "new_date": new_date,
        "new_start_time": new_start_time,
        "new_end_time": new_end_time,
        "new_description": new_description,
        "new_location": new_location,
    }


@tool(args_schema=ProposeDeleteEventArgs)
def propose_delete_event(event_id: str, event_title: str, event_datetime: str) -> dict:
    """Propose deleting a calendar event. Call get_calendar_events first to get event_id, event_title, and event_datetime."""
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
                duration_minutes=proposal.get("duration_minutes", 60),
                location=proposal.get("location", ""),
                description=proposal.get("description", ""),
            )

        elif proposal_type == "edit_event":
            return google_api.edit_event(
                event_id=proposal["event_id"],
                title=proposal.get("new_title"),
                date=proposal.get("new_date"),
                start_time=proposal.get("new_start_time"),
                end_time=proposal.get("new_end_time"),
                description=proposal.get("new_description"),
                location=proposal.get("new_location")
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
