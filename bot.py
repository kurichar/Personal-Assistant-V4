"""
Telegram bot for Personal Assistant.
Uses LangChain message format throughout.
"""

import logging
import json
import re
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)
from langchain_core.messages import HumanMessage

from config import TELEGRAM_BOT_TOKEN
import llm_handler
import tools
import agent_logger
import session
import database
import scheduler


# ============================================================
# HTML FORMATTING HELPERS
# ============================================================

def markdown_to_html(text: str) -> str:
    """
    Convert basic markdown to Telegram HTML format.
    Handles: **bold**, *italic*, `code`
    """
    if not text:
        return text

    # Escape HTML special chars first (except our markdown)
    text = text.replace('&', '&amp;')
    text = text.replace('<', '&lt;')
    text = text.replace('>', '&gt;')

    # Convert markdown to HTML
    # **bold** -> <b>bold</b>
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    # *italic* -> <i>italic</i> (but not if part of **)
    text = re.sub(r'(?<!\*)\*([^*]+?)\*(?!\*)', r'<i>\1</i>', text)
    # `code` -> <code>code</code>
    text = re.sub(r'`([^`]+?)`', r'<code>\1</code>', text)

    return text


# Logging setup
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Suppress noisy httpx polling logs
logging.getLogger("httpx").setLevel(logging.WARNING)


# ============================================================
# CONVERSATION STORAGE (LangChain messages)
# ============================================================

conversations: dict[int, list] = {}
pending_proposals: dict[int, list] = {}  # Queue of pending proposals awaiting confirmation


def get_conversation(user_id: int) -> list:
    """Get conversation history for user (LangChain messages)"""
    if user_id not in conversations:
        conversations[user_id] = []
    return conversations[user_id]


# How many messages to keep in conversation history
MAX_CONVERSATION_MESSAGES = 20  # Reduced from 50 - reasoning models are sensitive to context length


def add_message(user_id: int, message):
    """Add a LangChain message to conversation history"""
    conv = get_conversation(user_id)
    conv.append(message)
    # Keep only last N messages
    if len(conv) > MAX_CONVERSATION_MESSAGES:
        conversations[user_id] = conv[-MAX_CONVERSATION_MESSAGES:]


def clear_conversation(user_id: int):
    """Clear conversation history"""
    conversations[user_id] = []


# ============================================================
# COMMAND HANDLERS
# ============================================================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    user_id = update.effective_user.id
    clear_conversation(user_id)
    pending_proposals.pop(user_id, None)
    session.clear_session(user_id)  # Clear session state (cached IDs, freshness)

    # Create user in database if not exists
    if not database.get_user(user_id):
        database.create_user(user_id)
        logger.info(f"Created new user record for {user_id}")

    await update.message.reply_text(
        "Hi! I'm your personal assistant. I can help you manage your calendar and tasks.\n"
        "Just talk to me naturally and I'll do my best to help!\n\n"
        "Use /settings to configure notifications.",
        parse_mode='HTML'
    )


async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /settings command - show and modify notification preferences"""
    user_id = update.effective_user.id

    # Get or create user
    user = database.get_user(user_id)
    if not user:
        user = database.create_user(user_id)

    # Build settings display
    briefing_status = "On" if user['briefing_enabled'] else "Off"
    reminders_status = "On" if user['reminders_enabled'] else "Off"
    nudges_status = "On" if user['nudges_enabled'] else "Off"

    text = f"""<b>Notification Settings</b>

<b>Daily Briefing:</b> {briefing_status}
  Time: {user['briefing_time']}

<b>Event Reminders:</b> {reminders_status}
  (30 min before events)

<b>Overdue Task Nudges:</b> {nudges_status}

<b>Timezone:</b> {user['timezone']}

Tap a button to toggle:"""

    keyboard = [
        [InlineKeyboardButton(
            f"{'Disable' if user['briefing_enabled'] else 'Enable'} Briefing",
            callback_data="settings_toggle_briefing"
        )],
        [InlineKeyboardButton(
            f"{'Disable' if user['reminders_enabled'] else 'Enable'} Reminders",
            callback_data="settings_toggle_reminders"
        )],
        [InlineKeyboardButton(
            f"{'Disable' if user['nudges_enabled'] else 'Enable'} Nudges",
            callback_data="settings_toggle_nudges"
        )],
    ]

    await update.message.reply_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML'
    )


# ============================================================
# MESSAGE HANDLING
# ============================================================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle incoming user messages"""
    user_message = update.message.text
    user_id = update.effective_user.id

    logger.info(f"User {user_id}: {user_message}")
    agent_logger.log_user_message(user_id, user_message)

    # Add user message to conversation
    add_message(user_id, HumanMessage(content=user_message))

    # Process with LLM
    await process_llm_response(update, user_id)


async def process_llm_response(update: Update, user_id: int, max_iterations: int = 5):
    """
    Process LLM response, handling tool calls.
    Loops until we get a text response or hit max iterations.
    """
    for iteration in range(max_iterations):
        # Call LLM
        ai_msg = llm_handler.chat(get_conversation(user_id), tools=tools.ALL_TOOLS)

        # Check if LLM wants to call tools
        if not ai_msg.tool_calls:
            # No tool calls - just a text response
            add_message(user_id, ai_msg)
            agent_logger.log_final_response(ai_msg.content)
            await update.message.reply_text(
                markdown_to_html(ai_msg.content) or "I'm not sure how to help with that.",
                parse_mode='HTML'
            )
            return

        logger.info(f"LLM requested {len(ai_msg.tool_calls)} tool(s) (iteration {iteration + 1})")

        # Add AI message to conversation (contains all tool calls)
        add_message(user_id, ai_msg)

        # Collect proposals and execute read tools
        proposals_to_queue = []

        for tool_call in ai_msg.tool_calls:
            tool_name = tool_call["name"]
            tool_args = tool_call["args"]
            tool_id = tool_call["id"]

            # Check if this is a proposal tool (needs confirmation)
            if tool_name in tools.PROPOSAL_TOOL_NAMES:
                # Validate proposal against session state (ID exists, data fresh)
                user_session = session.get_session(user_id)
                validation_error = None

                # Validate event proposals
                if tool_name in ("propose_edit_event", "propose_delete_event"):
                    event_id = tool_args.get("event_id")
                    if event_id:
                        valid, error = user_session.validate_event_proposal(event_id)
                        if not valid:
                            validation_error = error

                # Validate task proposals
                elif tool_name in ("propose_edit_task", "propose_delete_task", "propose_complete_task"):
                    task_id = tool_args.get("task_id")
                    if task_id:
                        valid, error = user_session.validate_task_proposal(task_id)
                        if not valid:
                            validation_error = error

                # If validation failed, return error to LLM instead of queuing
                if validation_error:
                    logger.warning(f"Proposal validation failed: {validation_error}")
                    add_message(user_id, llm_handler.create_tool_message(
                        tool_id,
                        json.dumps({
                            "error": validation_error,
                            "action_required": "Fetch fresh data before proposing changes"
                        }, ensure_ascii=False)
                    ))
                    continue  # Skip this proposal, let LLM retry with fresh data

                # Execute the proposal tool to get the proposal data
                proposal_tool = next(t for t in tools.PROPOSAL_TOOLS if t.name == tool_name)
                proposal = proposal_tool.invoke(tool_args)

                # Queue this proposal
                proposals_to_queue.append({
                    "proposal": proposal,
                    "tool_call_id": tool_id,
                    "tool_name": tool_name,
                })

            else:
                # Read tool - execute immediately
                tool_func = next(t for t in tools.READ_TOOLS if t.name == tool_name)
                result = tool_func.invoke(tool_args)

                # Log tool execution
                agent_logger.log_tool_execution(tool_name, tool_args, result)

                # Update session state with fetched data
                user_session = session.get_session(user_id)
                if tool_name in ("get_calendar_events", "get_today_events"):
                    user_session.update_from_calendar_read(result)
                elif tool_name == "get_tasks":
                    user_session.update_from_tasks_read(result)

                # Add tool result to conversation
                add_message(user_id, llm_handler.create_tool_message(tool_id, json.dumps(result, ensure_ascii=False)))

        # If we have proposals, queue them and show the first one
        if proposals_to_queue:
            pending_proposals[user_id] = proposals_to_queue
            await show_next_proposal(update, user_id)
            return  # Wait for user to confirm/cancel/change

    # Hit max iterations
    await update.message.reply_text("I'm having trouble processing that. Can you try again?", parse_mode='HTML')


async def show_next_proposal(update: Update, user_id: int):
    """Show the next proposal in the queue"""
    queue = pending_proposals.get(user_id, [])

    if not queue:
        # No more proposals - let user know we're done
        await update.message.reply_text("All done!", parse_mode='HTML')
        return

    # Show count if multiple proposals
    total = len(queue)
    current_proposal = queue[0]
    proposal = current_proposal["proposal"]

    prefix = f"[1/{total}] " if total > 1 else ""
    await send_confirmation(update, user_id, proposal, prefix)


# ============================================================
# CONFIRMATION FLOW
# ============================================================

def format_proposal(proposal: dict) -> str:
    """Format a proposal for display to user with clear before/after for edits"""
    proposal_type = proposal.get("proposal_type", "unknown")

    # Human-readable action names
    action_names = {
        "create_task": "Create Task",
        "edit_task": "Edit Task",
        "delete_task": "Delete Task",
        "complete_task": "Complete Task",
        "create_event": "Create Event",
        "edit_event": "Edit Event",
        "delete_event": "Delete Event",
    }

    action_name = action_names.get(proposal_type, proposal_type)

    # Handle edit proposals with before/after format
    if proposal_type == "edit_event":
        return _format_edit_event_proposal(proposal, action_name)
    elif proposal_type == "edit_task":
        return _format_edit_task_proposal(proposal, action_name)
    else:
        return _format_simple_proposal(proposal, action_name)


def _format_edit_event_proposal(proposal: dict, action_name: str) -> str:
    """Format edit event proposal with before/after comparison"""
    lines = [f"**{action_name}**"]

    title = proposal.get("current_title", "Unknown")
    lines.append(f"  Event: {title}")

    # Current state (datetime string from LLM, e.g. "2025-12-26 10:00-11:00")
    current_datetime = proposal.get("current_datetime")
    if current_datetime:
        lines.append(f"  Currently: {current_datetime}")

    # Changes
    changes = []

    # Date change
    if proposal.get("new_date"):
        changes.append(f"    Date: -> {proposal['new_date']}")

    # Time changes (LLM provides both start and end when changing time)
    new_start = proposal.get("new_start_time")
    new_end = proposal.get("new_end_time")
    if new_start and new_end:
        changes.append(f"    Time: -> {new_start}-{new_end}")
    elif new_start:
        changes.append(f"    Start time: -> {new_start}")
    elif new_end:
        changes.append(f"    End time: -> {new_end}")

    # Title change
    if proposal.get("new_title"):
        changes.append(f"    Title: -> {proposal['new_title']}")

    # Location change
    if proposal.get("new_location"):
        changes.append(f"    Location: -> {proposal['new_location']}")

    # Description change
    if proposal.get("new_description"):
        changes.append(f"    Description: -> {proposal['new_description']}")

    if changes:
        lines.append("  Changes:")
        lines.extend(changes)

    return "\n".join(lines)


def _format_edit_task_proposal(proposal: dict, action_name: str) -> str:
    """Format edit task proposal with before/after comparison"""
    lines = [f"**{action_name}**"]

    title = proposal.get("current_title", "Unknown")
    lines.append(f"  Task: {title}")

    # Changes
    changes = []

    if proposal.get("new_title"):
        changes.append(f"    Title: {title} -> {proposal['new_title']}")

    if proposal.get("new_due_date"):
        changes.append(f"    Due date: {proposal['new_due_date']}")

    if proposal.get("new_notes"):
        changes.append(f"    Notes: {proposal['new_notes']}")

    if changes:
        lines.append("  Changes:")
        lines.extend(changes)

    return "\n".join(lines)


def _format_simple_proposal(proposal: dict, action_name: str) -> str:
    """Format non-edit proposals (create/delete/complete)"""
    # Keys to hide from user (internal IDs)
    hidden_keys = {"proposal_type", "task_id", "tasklist_id", "event_id",
                   "current_title", "current_datetime"}

    # Key display names (make more readable)
    key_display = {
        "task_title": "Task",
        "event_title": "Event",
        "event_datetime": "Scheduled",
        "title": "Title",
        "date": "Date",
        "time": "Time",
        "due_date": "Due date",
        "duration_minutes": "Duration (min)",
        "location": "Location",
        "description": "Description",
        "notes": "Notes",
    }

    # Format details (exclude hidden keys and None values)
    details = []
    for key, value in proposal.items():
        if key not in hidden_keys and value is not None and value != "":
            # Use display name or make key readable
            display_key = key_display.get(key, key.replace("_", " ").title())
            details.append(f"  {display_key}: {value}")

    details_text = "\n".join(details) if details else "  (no details)"

    return f"**{action_name}**\n{details_text}"


async def send_confirmation(update: Update, user_id: int, proposal: dict, prefix: str = ""):
    """Send confirmation prompt with buttons"""
    keyboard = [
        [
            InlineKeyboardButton("Confirm", callback_data=f"confirm_{user_id}"),
            InlineKeyboardButton("Cancel", callback_data=f"cancel_{user_id}"),
        ],
        [InlineKeyboardButton("Change", callback_data=f"change_{user_id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    message_text = f"{prefix}Proposed action:\n\n{markdown_to_html(format_proposal(proposal))}\n\nConfirm?"

    await update.message.reply_text(message_text, reply_markup=reply_markup, parse_mode='HTML')


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle button presses (Confirm/Cancel/Change/Settings)"""
    query = update.callback_query
    await query.answer()

    data = query.data
    user_id = update.effective_user.id

    if data.startswith("confirm_"):
        await handle_confirm(query, user_id)
    elif data.startswith("cancel_"):
        await handle_cancel(query, user_id)
    elif data.startswith("change_"):
        await handle_change(query, user_id)
    elif data.startswith("settings_toggle_"):
        await handle_settings_toggle(query, user_id, data, context)


async def handle_confirm(query, user_id: int):
    """Execute the confirmed proposal and show next in queue"""
    queue = pending_proposals.get(user_id, [])

    if not queue:
        await query.edit_message_text("No pending action to confirm.")
        return

    # Pop the first proposal from queue
    current = queue.pop(0)
    proposal = current["proposal"]
    tool_call_id = current["tool_call_id"]

    # Execute the proposal
    result = tools.execute_confirmed_proposal(proposal)

    # Log the execution
    agent_logger.log_tool_execution(f"execute_{proposal.get('proposal_type')}", proposal, result)

    # Add tool result to conversation
    add_message(user_id, llm_handler.create_tool_message(tool_call_id, json.dumps(result, ensure_ascii=False)))

    # Check if there are more proposals in queue
    if queue:
        remaining = len(queue)
        next_proposal = queue[0]["proposal"]
        prefix = f"[1/{remaining}] " if remaining > 1 else ""

        # Brief acknowledgment + show next proposal
        ack = "Done!" if result.get("success") else f"Error: {result.get('error')}"
        await query.edit_message_text(ack, parse_mode='HTML')
        await query.message.reply_text(
            f"{prefix}Proposed action:\n\n{markdown_to_html(format_proposal(next_proposal))}\n\nConfirm?",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("Confirm", callback_data=f"confirm_{user_id}"),
                    InlineKeyboardButton("Cancel", callback_data=f"cancel_{user_id}"),
                ],
                [InlineKeyboardButton("Change", callback_data=f"change_{user_id}")]
            ]),
            parse_mode='HTML'
        )
    else:
        # No more proposals - get LLM response
        pending_proposals.pop(user_id, None)
        await query.edit_message_text("Confirmed")

        # Get natural LLM follow-up
        ai_msg = llm_handler.chat(get_conversation(user_id), tools=tools.ALL_TOOLS)

        # Handle potential tool calls in follow-up (unlikely but possible)
        if ai_msg.tool_calls:
            add_message(user_id, ai_msg)
            # Process any new proposals
            proposals_to_queue = []
            for tool_call in ai_msg.tool_calls:
                tool_name = tool_call["name"]
                tool_args = tool_call["args"]
                tool_id = tool_call["id"]

                if tool_name in tools.PROPOSAL_TOOL_NAMES:
                    # Validate proposal against session state
                    user_session = session.get_session(user_id)
                    validation_error = None

                    if tool_name in ("propose_edit_event", "propose_delete_event"):
                        event_id = tool_args.get("event_id")
                        if event_id:
                            valid, error = user_session.validate_event_proposal(event_id)
                            if not valid:
                                validation_error = error
                    elif tool_name in ("propose_edit_task", "propose_delete_task", "propose_complete_task"):
                        task_id = tool_args.get("task_id")
                        if task_id:
                            valid, error = user_session.validate_task_proposal(task_id)
                            if not valid:
                                validation_error = error

                    if validation_error:
                        add_message(user_id, llm_handler.create_tool_message(
                            tool_id,
                            json.dumps({"error": validation_error, "action_required": "Fetch fresh data first"}, ensure_ascii=False)
                        ))
                        continue

                    proposal_tool = next(t for t in tools.PROPOSAL_TOOLS if t.name == tool_name)
                    new_proposal = proposal_tool.invoke(tool_args)
                    proposals_to_queue.append({
                        "proposal": new_proposal,
                        "tool_call_id": tool_id,
                        "tool_name": tool_name,
                    })
                else:
                    tool_func = next(t for t in tools.READ_TOOLS if t.name == tool_name)
                    res = tool_func.invoke(tool_args)

                    # Update session state
                    user_session = session.get_session(user_id)
                    if tool_name in ("get_calendar_events", "get_today_events"):
                        user_session.update_from_calendar_read(res)
                    elif tool_name == "get_tasks":
                        user_session.update_from_tasks_read(res)

                    add_message(user_id, llm_handler.create_tool_message(tool_id, json.dumps(res, ensure_ascii=False)))

            if proposals_to_queue:
                pending_proposals[user_id] = proposals_to_queue
                total = len(proposals_to_queue)
                prefix = f"[1/{total}] " if total > 1 else ""
                await query.message.reply_text(
                    f"{prefix}Proposed action:\n\n{markdown_to_html(format_proposal(proposals_to_queue[0]['proposal']))}\n\nConfirm?",
                    reply_markup=InlineKeyboardMarkup([
                        [
                            InlineKeyboardButton("Confirm", callback_data=f"confirm_{user_id}"),
                            InlineKeyboardButton("Cancel", callback_data=f"cancel_{user_id}"),
                        ],
                        [InlineKeyboardButton("Change", callback_data=f"change_{user_id}")]
                    ]),
                    parse_mode='HTML'
                )
                return

        # Just a text response - show it
        if ai_msg.content:
            add_message(user_id, ai_msg)
            agent_logger.log_final_response(ai_msg.content)
            await query.message.reply_text(markdown_to_html(ai_msg.content), parse_mode='HTML')


async def handle_cancel(query, user_id: int):
    """Cancel all pending proposals"""
    queue = pending_proposals.pop(user_id, [])

    # Add cancellation messages for all proposals
    for item in queue:
        add_message(user_id, llm_handler.create_tool_message(
            item["tool_call_id"],
            json.dumps({"status": "cancelled", "message": "User cancelled the action"}, ensure_ascii=False)
        ))

    if len(queue) > 1:
        await query.edit_message_text(f"Cancelled {len(queue)} pending actions.")
    else:
        await query.edit_message_text("Cancelled.")


async def handle_change(query, user_id: int):
    """Handle request to change the current proposal"""
    queue = pending_proposals.get(user_id, [])

    if not queue:
        await query.edit_message_text("No pending action to change.")
        return

    # Get current proposal (first in queue)
    current = queue[0]
    proposal = current["proposal"]
    tool_call_id = current["tool_call_id"]

    # Add tool result indicating user wants changes
    add_message(user_id, llm_handler.create_tool_message(
        tool_call_id,
        json.dumps({
            "status": "change_requested",
            "message": "User wants to modify this proposal. Ask what they'd like to change.",
            "original_proposal": proposal
        }, ensure_ascii=False)
    ))

    # Clear all pending proposals (user will make a new request)
    pending_proposals.pop(user_id, None)

    await query.edit_message_text(
        f"Current proposal:\n{markdown_to_html(format_proposal(proposal))}\n\n"
        "What would you like to change? (Just type your response)",
        parse_mode='HTML'
    )


async def handle_settings_toggle(query, user_id: int, data: str, context: ContextTypes.DEFAULT_TYPE):
    """Handle settings toggle button presses"""
    user = database.get_user(user_id)
    if not user:
        await query.edit_message_text("Error: User not found. Use /start first.")
        return

    # Determine which setting to toggle
    if data == "settings_toggle_briefing":
        new_value = 0 if user['briefing_enabled'] else 1
        database.update_user(user_id, briefing_enabled=new_value)

        # Schedule or remove briefing job
        if new_value:
            scheduler.schedule_user_briefing(
                context.application,
                user_id,
                user['briefing_time'],
                user['timezone']
            )
        else:
            scheduler.remove_user_briefing(context.application, user_id)

    elif data == "settings_toggle_reminders":
        new_value = 0 if user['reminders_enabled'] else 1
        database.update_user(user_id, reminders_enabled=new_value)

    elif data == "settings_toggle_nudges":
        new_value = 0 if user['nudges_enabled'] else 1
        database.update_user(user_id, nudges_enabled=new_value)

    # Refresh and show updated settings
    user = database.get_user(user_id)
    briefing_status = "On" if user['briefing_enabled'] else "Off"
    reminders_status = "On" if user['reminders_enabled'] else "Off"
    nudges_status = "On" if user['nudges_enabled'] else "Off"

    text = f"""<b>Notification Settings</b>

<b>Daily Briefing:</b> {briefing_status}
  Time: {user['briefing_time']}

<b>Event Reminders:</b> {reminders_status}
  (30 min before events)

<b>Overdue Task Nudges:</b> {nudges_status}

<b>Timezone:</b> {user['timezone']}

Tap a button to toggle:"""

    keyboard = [
        [InlineKeyboardButton(
            f"{'Disable' if user['briefing_enabled'] else 'Enable'} Briefing",
            callback_data="settings_toggle_briefing"
        )],
        [InlineKeyboardButton(
            f"{'Disable' if user['reminders_enabled'] else 'Enable'} Reminders",
            callback_data="settings_toggle_reminders"
        )],
        [InlineKeyboardButton(
            f"{'Disable' if user['nudges_enabled'] else 'Enable'} Nudges",
            callback_data="settings_toggle_nudges"
        )],
    ]

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML'
    )


# ============================================================
# BOT STARTUP
# ============================================================

def run_bot():
    """Start the Telegram bot"""
    # Initialize database
    database.init_db()
    logger.info("Database initialized")

    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Add handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("settings", settings_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(CallbackQueryHandler(handle_callback))

    # Set up scheduled jobs for proactive notifications
    scheduler.setup_scheduled_jobs(application)
    logger.info("Scheduled jobs initialized")

    logger.info("Bot starting...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    run_bot()
