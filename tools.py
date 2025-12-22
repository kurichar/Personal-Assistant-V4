READ_TOOLS = {
    "get_calendar_events": {
        "function": google_api.get_events,
        "description": "Get calendar events for a date range",
        "parameters": {...}
    },
    "get_tasks": {
        "function": google_api.get_tasks,
        "description": "Get all tasks",
        "parameters": {...}
    }
}

WRITE_TOOLS = {
    "create_task": {
        "function": google_api.create_task,
        "description": "Create a new task",
        "parameters": {...},
        "needs_confirmation": True
    },
    "create_event": {
        "function": google_api.create_event,
        "description": "Create calendar event",
        "parameters": {...},
        "needs_confirmation": True
    }
}

ALL_TOOLS = {**READ_TOOLS, **WRITE_TOOLS}