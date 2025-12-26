import os
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)

# Scopes - what permissions we need (full access for CRUD)
SCOPES = [
    'https://www.googleapis.com/auth/calendar',
    'https://www.googleapis.com/auth/tasks',
]

# Token file (stores auth after first login)
TOKEN_FILE = 'token.json'
CREDENTIALS_FILE = 'credentials.json'


def get_credentials():
    """Get or refresh Google API credentials"""
    creds = None
    
    # Load existing token
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    
    # If no valid credentials, authenticate
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            logger.info("Refreshing credentials")
            creds.refresh(Request())
        else:
            logger.info("Starting OAuth flow - browser will open")
            flow = InstalledAppFlow.from_client_secrets_file(
                CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        
        # Save credentials for next time
        with open(TOKEN_FILE, 'w') as token:
            token.write(creds.to_json())
        logger.info("Credentials saved")
    
    return creds


def get_calendar_service():
    """Get Google Calendar service"""
    creds = get_credentials()
    return build('calendar', 'v3', credentials=creds)


def get_tasks_service():
    """Get Google Tasks service"""
    creds = get_credentials()
    return build('tasks', 'v1', credentials=creds)


# ============================================================
# CALENDAR FUNCTIONS
# ============================================================

def get_events(days_ahead=7):
    """
    Get calendar events for the next N days
    
    Args:
        days_ahead: How many days to look ahead (default 7)
    
    Returns:
        List of events with relevant info
    """
    try:
        service = get_calendar_service()
        # Time range
        now = datetime.now(ZoneInfo("Asia/Jerusalem"))
        time_min = now.isoformat()
        time_max = (now + timedelta(days=days_ahead)).isoformat()

        logger.info(f"Fetching events from {time_min} to {time_max}")
        
        # Call the Calendar API
        events_result = service.events().list(
            calendarId='primary',
            timeMin=time_min,
            timeMax=time_max,
            maxResults=50,
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        
        events = events_result.get('items', [])
        
        # Format events for LLM (include ID for edit/delete)
        formatted_events = []
        for event in events:
            start = event['start'].get('dateTime', event['start'].get('date'))
            formatted_events.append({
                'id': event.get('id'),
                'summary': event.get('summary', 'No title'),
                'start': start,
                'description': event.get('description', ''),
                'location': event.get('location', '')
            })
        
        logger.info(f"Found {len(formatted_events)} events")
        return formatted_events
    
    except Exception as e:
        logger.error(f"Error fetching calendar events: {e}")
        return []


def get_today_events():
    """Get events for today only"""
    return get_events(days_ahead=1)


def create_event(title, date, time=None, description='', location='', duration_minutes=60):
    """
    Create a new calendar event

    Args:
        title: Event title/summary
        date: Date string (YYYY-MM-DD)
        time: Time string (HH:MM) in 24h format, or None for all-day event
        description: Event description
        location: Event location
        duration_minutes: Duration in minutes (default 60)

    Returns:
        Created event info or error
    """
    try:
        service = get_calendar_service()

        if time:
            # Timed event
            tz = ZoneInfo("Asia/Jerusalem")
            start_datetime = datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M").replace(tzinfo=tz)
            end_datetime = start_datetime + timedelta(minutes=duration_minutes)

            event = {
                "summary": title,
                "description": description,
                "location": location,
                "start": {"dateTime": start_datetime.isoformat()},
                "end": {"dateTime": end_datetime.isoformat()},
            }
        else:
            # All-day event
            event = {
                "summary": title,
                "description": description,
                "location": location,
                "start": {"date": date},
                "end": {"date": (datetime.fromisoformat(date) + timedelta(days=1)).date().isoformat()},
            }

        created_event = service.events().insert(calendarId='primary', body=event).execute()
        logger.info(f"Created event: {created_event.get('summary')}")

        return {
            'success': True,
            'message': f"Created event '{title}'",
            'event_id': created_event.get('id')
        }

    except Exception as e:
        logger.error(f"Error creating event: {e}")
        return {'success': False, 'error': str(e)}


def edit_event(event_id, title=None, date=None, start_time=None, end_time=None, description=None, location=None):
    """
    Edit an existing calendar event

    Args:
        event_id: ID of the event to edit
        title: New title (optional)
        date: New date YYYY-MM-DD (optional)
        start_time: New start time HH:MM (optional)
        end_time: New end time HH:MM (optional)
        description: New description (optional)
        location: New location (optional)

    Returns:
        Updated event info or error
    """
    try:
        service = get_calendar_service()

        # Get existing event
        event = service.events().get(calendarId='primary', eventId=event_id).execute()

        # Update fields if provided
        if title:
            event['summary'] = title
        if description is not None:
            event['description'] = description
        if location is not None:
            event['location'] = location

        # Handle date/time changes
        is_all_day = 'date' in event.get('start', {})

        if is_all_day:
            # For all-day events, only update date
            if date:
                event['start'] = {'date': date}
                event['end'] = {'date': date}
        elif date or start_time or end_time:
            # For timed events - get existing values
            existing_start = datetime.fromisoformat(event['start']['dateTime'])
            existing_end = datetime.fromisoformat(event['end']['dateTime'])
            existing_tz = existing_start.tzinfo or ZoneInfo('UTC')

            # Determine new date (use existing if not provided)
            new_date = datetime.fromisoformat(date).date() if date else existing_start.date()

            # Determine new start time
            if start_time:
                new_start_time = datetime.strptime(start_time, "%H:%M").time()
            else:
                new_start_time = existing_start.time()

            # Determine new end time
            if end_time:
                new_end_time = datetime.strptime(end_time, "%H:%M").time()
            else:
                # If only start_time changed, shift end by same amount to preserve duration
                if start_time and not end_time:
                    original_duration = existing_end - existing_start
                    new_start_dt = datetime.combine(new_date, new_start_time).replace(tzinfo=existing_tz)
                    new_end_dt = new_start_dt + original_duration
                    new_end_time = new_end_dt.time()
                else:
                    new_end_time = existing_end.time()

            # Build new datetime objects
            new_start_dt = datetime.combine(new_date, new_start_time).replace(tzinfo=existing_tz)
            new_end_dt = datetime.combine(new_date, new_end_time).replace(tzinfo=existing_tz)

            event['start'] = {'dateTime': new_start_dt.isoformat(), 'timeZone': str(existing_tz)}
            event['end'] = {'dateTime': new_end_dt.isoformat(), 'timeZone': str(existing_tz)}

        updated_event = service.events().update(calendarId='primary', eventId=event_id, body=event).execute()
        logger.info(f"Updated event: {updated_event.get('summary')}")

        return {
            'success': True,
            'message': f"Updated event '{updated_event.get('summary')}'"
        }

    except Exception as e:
        logger.error(f"Error editing event: {e}")
        return {'success': False, 'error': str(e)}


def delete_event(event_id):
    """
    Delete a calendar event

    Args:
        event_id: ID of the event to delete

    Returns:
        Success/error message
    """
    try:
        service = get_calendar_service()
        service.events().delete(calendarId='primary', eventId=event_id).execute()
        logger.info(f"Deleted event: {event_id}")

        return {'success': True, 'message': 'Event deleted'}

    except Exception as e:
        logger.error(f"Error deleting event: {e}")
        return {'success': False, 'error': str(e)}


# ============================================================
# TASKS FUNCTIONS
# ============================================================

def get_tasks():
    """
    Get all tasks from all task lists

    Returns:
        List of tasks with relevant info
    """
    try:
        service = get_tasks_service()

        # Get all task lists
        tasklists = service.tasklists().list().execute()

        all_tasks = []

        for tasklist in tasklists.get('items', []):
            # Get tasks from this list
            tasks_result = service.tasks().list(
                tasklist=tasklist['id'],
                showCompleted=False  # Only incomplete tasks
            ).execute()

            tasks = tasks_result.get('items', [])

            for task in tasks:
                all_tasks.append({
                    'id': task.get('id'),
                    'tasklist_id': tasklist['id'],
                    'title': task.get('title', 'No title'),
                    'notes': task.get('notes', ''),
                    'due': task.get('due', ''),
                    'list': tasklist.get('title', 'Default')
                })

        logger.info(f"Found {len(all_tasks)} tasks")
        return all_tasks

    except Exception as e:
        logger.error(f"Error fetching tasks: {e}")
        return []


def get_default_tasklist_id():
    """Get the ID of the default task list"""
    try:
        service = get_tasks_service()
        tasklists = service.tasklists().list().execute()
        items = tasklists.get('items', [])
        if items:
            return items[0]['id']
        return None
    except Exception as e:
        logger.error(f"Error getting default tasklist: {e}")
        return None


def create_task(title, notes='', due_date=None, tasklist_id=None):
    """
    Create a new task

    Args:
        title: Task title
        notes: Task notes/description
        due_date: Due date (YYYY-MM-DD)
        tasklist_id: ID of task list (uses default if not provided)

    Returns:
        Created task info or error
    """
    try:
        service = get_tasks_service()

        if not tasklist_id:
            tasklist_id = get_default_tasklist_id()

        task = {
            'title': title,
            'notes': notes,
        }

        if due_date:
            task['due'] = f"{due_date}T00:00:00.000Z"

        created_task = service.tasks().insert(tasklist=tasklist_id, body=task).execute()
        logger.info(f"Created task: {created_task.get('title')}")

        return {
            'success': True,
            'message': f"Created task '{title}'",
            'task_id': created_task.get('id')
        }

    except Exception as e:
        logger.error(f"Error creating task: {e}")
        return {'success': False, 'error': str(e)}


def edit_task(task_id, tasklist_id=None, title=None, notes=None, due_date=None):
    """
    Edit an existing task

    Args:
        task_id: ID of task to edit
        tasklist_id: ID of task list (uses default if not provided)
        title: New title (optional)
        notes: New notes (optional)
        due_date: New due date YYYY-MM-DD (optional)

    Returns:
        Updated task info or error
    """
    try:
        service = get_tasks_service()

        if not tasklist_id:
            tasklist_id = get_default_tasklist_id()

        # Get existing task
        task = service.tasks().get(tasklist=tasklist_id, task=task_id).execute()

        # Update fields if provided
        if title:
            task['title'] = title
        if notes is not None:
            task['notes'] = notes
        if due_date:
            task['due'] = f"{due_date}T00:00:00.000Z"

        updated_task = service.tasks().update(tasklist=tasklist_id, task=task_id, body=task).execute()
        logger.info(f"Updated task: {updated_task.get('title')}")

        return {
            'success': True,
            'message': f"Updated task '{updated_task.get('title')}'"
        }

    except Exception as e:
        logger.error(f"Error editing task: {e}")
        return {'success': False, 'error': str(e)}


def delete_task(task_id, tasklist_id=None):
    """
    Delete a task

    Args:
        task_id: ID of task to delete
        tasklist_id: ID of task list (uses default if not provided)

    Returns:
        Success/error message
    """
    try:
        service = get_tasks_service()

        if not tasklist_id:
            tasklist_id = get_default_tasklist_id()

        service.tasks().delete(tasklist=tasklist_id, task=task_id).execute()
        logger.info(f"Deleted task: {task_id}")

        return {'success': True, 'message': 'Task deleted'}

    except Exception as e:
        logger.error(f"Error deleting task: {e}")
        return {'success': False, 'error': str(e)}


def complete_task(task_id, tasklist_id=None):
    """
    Mark a task as completed

    Args:
        task_id: ID of task to complete
        tasklist_id: ID of task list (uses default if not provided)

    Returns:
        Success/error message
    """
    try:
        service = get_tasks_service()

        if not tasklist_id:
            tasklist_id = get_default_tasklist_id()

        # Get existing task
        task = service.tasks().get(tasklist=tasklist_id, task=task_id).execute()

        # Mark as completed
        task['status'] = 'completed'

        updated_task = service.tasks().update(tasklist=tasklist_id, task=task_id, body=task).execute()
        logger.info(f"Completed task: {updated_task.get('title')}")

        return {
            'success': True,
            'message': f"Completed task '{updated_task.get('title')}'"
        }

    except Exception as e:
        logger.error(f"Error completing task: {e}")
        return {'success': False, 'error': str(e)}


# ============================================================
# TEST FUNCTIONS
# ============================================================

if __name__ == '__main__':
    # Test authentication and API calls
    logging.basicConfig(level=logging.INFO)
    
    print("Testing Google Calendar API...")
    events = get_today_events()
    print(f"\nToday's events: {len(events)}")
    for event in events:
        print(f"  - {event['summary']} at {event['start']}")
    
    print("\nTesting Google Tasks API...")
    tasks = get_tasks()
    print(f"\nActive tasks: {len(tasks)}")
    for task in tasks:
        print(f"  - {task['title']} (in {task['list']})")