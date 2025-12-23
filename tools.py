import logging
from typing import Dict, List, Any
import google_api
import agent_logger

logger = logging.getLogger(__name__)


# ============================================================
# TOOL DEFINITIONS (for LLM)
# ============================================================

READ_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_calendar_events",
            "description": "Get calendar events for the next N days. Use this when the user asks about their schedule, what's coming up, or what they have planned.",
            "parameters": {
                "type": "object",
                "properties": {
                    "days_ahead": {
                        "type": "integer",
                        "description": "Number of days to look ahead (default 7)",
                        "default": 7
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_today_events",
            "description": "Get events for today only. Use this when user asks specifically about today.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_tasks",
            "description": "Get all incomplete tasks. Use this when user asks about their tasks, todos, or what they need to do.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    }
]





# Write tools will come later
WRITE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "propose_action",
            "description": "Use this to propose any write action (create/edit/delete events or tasks). The user will be asked to confirm before it executes. ALWAYS use this instead of directly modifying data.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action_type": {
                        "type": "string",
                        "enum": ["create_event", "edit_event", "delete_event", "create_task", "edit_task", "delete_task", "complete_task"],
                        "description": "What kind of action to perform"
                    },
                    "description": {
                        "type": "string",
                        "description": "Human-readable description of what will happen, e.g. 'Delete task: go to doctor'"
                    },
                    "details": {
                        "type": "object",
                        "description": "The specific parameters for the action (event title, date, task name, etc.)"
                    }
                },
                "required": ["action_type", "description", "details"]
            }
        }
    }
]

ALL_TOOLS = READ_TOOLS + WRITE_TOOLS


# ============================================================
# TOOL EXECUTION
# ============================================================

def execute_tool(tool_name: str, arguments: Dict[str, Any]) -> Any:
    """
    Execute a tool by name with given arguments

    Args:
        tool_name: Name of the tool to execute
        arguments: Dictionary of arguments for the tool

    Returns:
        Result from the tool execution
    """
    logger.info(f"Executing tool: {tool_name}")

    try:
        result = _execute_tool_inner(tool_name, arguments)
        agent_logger.log_tool_execution(tool_name, arguments, result)
        return result
    except Exception as e:
        logger.error(f"Error executing tool {tool_name}: {e}")
        error_result = {"error": str(e)}
        agent_logger.log_tool_execution(tool_name, arguments, error_result)
        return error_result


def _execute_tool_inner(tool_name: str, arguments: Dict[str, Any]) -> Any:
    """Inner function that actually executes the tool"""
    # ============ READ TOOLS ============
    if tool_name == "get_calendar_events":
        days_ahead = arguments.get('days_ahead', 7)
        return google_api.get_events(days_ahead=days_ahead)

    elif tool_name == "get_today_events":
        return google_api.get_today_events()

    elif tool_name == "get_tasks":
        return google_api.get_tasks()

    # ============ CALENDAR WRITE TOOLS ============
    elif tool_name == "create_event":
        return google_api.create_event(
            title=arguments.get('title', arguments.get('event_title', 'Untitled Event')),
            date=arguments.get('date'),
            time=arguments.get('time'),
            description=arguments.get('description', ''),
            location=arguments.get('location', ''),
            duration_hours=arguments.get('duration_hours', 1)
        )

    elif tool_name == "edit_event":
        return google_api.edit_event(
            event_id=arguments.get('event_id'),
            title=arguments.get('title'),
            date=arguments.get('date'),
            time=arguments.get('time'),
            description=arguments.get('description'),
            location=arguments.get('location')
        )

    elif tool_name == "delete_event":
        return google_api.delete_event(
            event_id=arguments.get('event_id')
        )

    # ============ TASK WRITE TOOLS ============
    elif tool_name == "create_task":
        return google_api.create_task(
            title=arguments.get('title', 'Untitled Task'),
            notes=arguments.get('notes', ''),
            due_date=arguments.get('due_date'),
            tasklist_id=arguments.get('tasklist_id')
        )

    elif tool_name == "edit_task":
        return google_api.edit_task(
            task_id=arguments.get('task_id'),
            tasklist_id=arguments.get('tasklist_id'),
            title=arguments.get('title'),
            notes=arguments.get('notes'),
            due_date=arguments.get('due_date')
        )

    elif tool_name == "delete_task":
        return google_api.delete_task(
            task_id=arguments.get('task_id'),
            tasklist_id=arguments.get('tasklist_id')
        )

    elif tool_name == "complete_task":
        return google_api.complete_task(
            task_id=arguments.get('task_id'),
            tasklist_id=arguments.get('tasklist_id')
        )

    else:
        raise ValueError(f"Unknown tool: {tool_name}")


def execute_tool_calls(tool_calls: List[Dict]) -> List[Dict]:
    """
    Execute multiple tool calls and return results
    
    Args:
        tool_calls: List of tool call dictionaries from LLM
    
    Returns:
        List of results formatted for LLM
    """
    results = []
    
    for tool_call in tool_calls:
        function = tool_call['function']
        tool_name = function['name']
        arguments = function.get('arguments', {})
        
        # Execute the tool
        result = execute_tool(tool_name, arguments)
        
        # Format for LLM
        results.append({
            "role": "tool",
            "content": str(result),
            "tool_call_id": tool_call.get('id', tool_name)
        })
    
    return results