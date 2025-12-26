"""
Pydantic schemas for tool arguments.
These define the exact structure the LLM must follow when calling tools.
"""

from pydantic import BaseModel, Field
from typing import Optional


# ============================================================
# READ TOOL SCHEMAS
# ============================================================

class GetCalendarEventsArgs(BaseModel):
    """Arguments for getting calendar events"""
    days_ahead: int = Field(
        default=7,
        ge=1,
        le=30,
        description="Number of days to look ahead (1-30)"
    )


# ============================================================
# PROPOSAL SCHEMAS - Tasks
# ============================================================

class ProposeCreateTaskArgs(BaseModel):
    """Arguments for proposing a new task"""
    title: str = Field(
        min_length=1,
        description="The task title - be specific and actionable"
    )
    notes: str = Field(
        default="",
        description="Optional additional notes or details"
    )
    due_date: Optional[str] = Field(
        default=None,
        pattern=r"^\d{4}-\d{2}-\d{2}$",
        description="Due date in YYYY-MM-DD format (e.g., 2025-01-15)"
    )


class ProposeEditTaskArgs(BaseModel):
    """Arguments for proposing to edit an existing task"""
    task_id: str = Field(
        description="The ID of the task to edit (from get_tasks)"
    )
    current_title: str = Field(
        description="The current title of the task (from get_tasks)"
    )
    tasklist_id: str = Field(
        description="The task list ID (from get_tasks)"
    )
    title: Optional[str] = Field(
        default=None,
        min_length=1,
        description="New title for the task"
    )
    notes: Optional[str] = Field(
        default=None,
        description="New notes for the task"
    )
    due_date: Optional[str] = Field(
        default=None,
        pattern=r"^\d{4}-\d{2}-\d{2}$",
        description="New due date in YYYY-MM-DD format"
    )


class ProposeDeleteTaskArgs(BaseModel):
    """Arguments for proposing to delete a task"""
    task_id: str = Field(
        description="The ID of the task to delete (from get_tasks)"
    )
    task_title: str = Field(
        description="The title of the task being deleted (from get_tasks)"
    )
    tasklist_id: str = Field(
        description="The task list ID (from get_tasks)"
    )


class ProposeCompleteTaskArgs(BaseModel):
    """Arguments for proposing to mark a task as complete"""
    task_id: str = Field(
        description="The ID of the task to complete (from get_tasks)"
    )
    task_title: str = Field(
        description="The title of the task being completed (from get_tasks)"
    )
    tasklist_id: str = Field(
        description="The task list ID (from get_tasks)"
    )


# ============================================================
# PROPOSAL SCHEMAS - Calendar Events
# ============================================================

class ProposeCreateEventArgs(BaseModel):
    """Arguments for proposing a new calendar event"""
    title: str = Field(
        min_length=1,
        description="Event title/summary"
    )
    date: str = Field(
        pattern=r"^\d{4}-\d{2}-\d{2}$",
        description="Event date in YYYY-MM-DD format (e.g., 2025-01-15)"
    )
    time: Optional[str] = Field(
        default=None,
        pattern=r"^\d{2}:\d{2}$",
        description="Event time in HH:MM 24-hour format (e.g., 14:30). Omit for all-day event."
    )
    duration_minutes: int = Field(
        default=60,
        ge=5,
        le=1440,
        description="Event duration in minutes (5-1440, i.e., 5 min to 24 hours). Examples: 15, 30, 60, 90, 120"
    )
    location: str = Field(
        default="",
        description="Event location"
    )
    description: str = Field(
        default="",
        description="Event description or notes"
    )


class ProposeEditEventArgs(BaseModel):
    """Arguments for proposing to edit a calendar event"""
    event_id: str = Field(
        description="The ID of the event to edit (from get_calendar_events)"
    )
    current_title: str = Field(
        description="Current title of the event (from get_calendar_events)"
    )
    current_datetime: str = Field(
        description="Current date/time of the event (from get_calendar_events 'start' field)"
    )
    new_title: Optional[str] = Field(
        default=None,
        description="New title for the event"
    )
    new_date: Optional[str] = Field(
        default=None,
        pattern=r"^\d{4}-\d{2}-\d{2}$",
        description="New date in YYYY-MM-DD format"
    )
    new_start_time: Optional[str] = Field(
        default=None,
        pattern=r"^\d{2}:\d{2}$",
        description="New start time in HH:MM format (24-hour). Provide with new_end_time."
    )
    new_end_time: Optional[str] = Field(
        default=None,
        pattern=r"^\d{2}:\d{2}$",
        description="New end time in HH:MM format (24-hour). Provide with new_start_time."
    )
    new_description: Optional[str] = Field(
        default=None,
        description="New description for the event"
    )
    new_location: Optional[str] = Field(
        default=None,
        description="New location for the event"
    )


class ProposeDeleteEventArgs(BaseModel):
    """Arguments for proposing to delete a calendar event"""
    event_id: str = Field(
        description="The ID of the event to delete (from get_calendar_events)"
    )
    event_title: str = Field(
        description="The title of the event being deleted (from get_calendar_events)"
    )
    event_datetime: str = Field(
        description="The date/time of the event (from get_calendar_events 'start' field)"
    )