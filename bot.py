import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from telegram import InlineKeyboardMarkup, InlineKeyboardButton

from config import TELEGRAM_BOT_TOKEN
import llm_handler
import tools
import agent_logger

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Simple in-memory conversation storage
conversations = {}


def get_conversation(user_id: int) -> list:
    """Get conversation history for user"""
    if user_id not in conversations:
        conversations[user_id] = []
    return conversations[user_id]


def add_to_conversation(user_id: int, message: dict):
    """Add message to conversation history"""
    conv = get_conversation(user_id)
    conv.append(message)
    
    # Keep only last 20 messages
    if len(conv) > 20:
        conversations[user_id] = conv[-20:]


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    user_id = update.effective_user.id
    
    # Clear conversation
    conversations[user_id] = []
    
    await update.message.reply_text(
        "Hi Ariel! I'm your personal assistant. I can help you manage your calendar and tasks.\n"
        "Just talk to me naturally and I'll do my best to help!"
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle incoming messages"""
    user_message = update.message.text
    user_id = update.effective_user.id

    logger.info(f"User {user_id} said: {user_message}")

    # Log to detailed agent log
    agent_logger.log_user_message(user_id, user_message)

    # Add user message to conversation
    add_to_conversation(user_id, {"role": "user", "content": user_message})

    # Call LLM with all tools (read + write)
    response = llm_handler.chat(get_conversation(user_id), tools=tools.ALL_TOOLS)

    # Loop until we get a text response (max 5 iterations to prevent infinite loops)
    max_iterations = 5
    iteration = 0

    while response.has_tool_calls() and iteration < max_iterations:
        iteration += 1
        logger.info(f"LLM requested {len(response.tool_calls)} tool call(s) (iteration {iteration})")

        # Check if any tool call is propose_action (needs confirmation)
        for tool_call in response.tool_calls:
            tool_name = tool_call['function']['name']
            arguments = tool_call['function']['arguments']

            if tool_name == "propose_action":
                # Log what the LLM is proposing
                logger.info(f"Propose action arguments: {arguments}")

                action_type = arguments.get('action_type', 'unknown')
                details = arguments.get('details', {})
                description = arguments.get('description', '')

                # Build a detailed confirmation message
                details_text = "\n".join([f"  • {k}: {v}" for k, v in details.items()])
                full_description = f"{description}\n\n📝 Details:\n{details_text}" if details_text else description

                # Show confirmation UI instead of executing
                await send_confirmation(
                    update,
                    user_id,
                    full_description,
                    {
                        'tool': action_type,
                        'args': details
                    }
                )
                return  # Wait for button press, don't add to conversation

        # For read tools, execute normally
        add_to_conversation(user_id, {
            "role": "assistant",
            "content": response.text or "",
            "tool_calls": response.tool_calls
        })

        # Execute the tools
        tool_results = tools.execute_tool_calls(response.tool_calls)

        # Add tool results to conversation
        for result in tool_results:
            add_to_conversation(user_id, result)

        # Get next response from LLM
        response = llm_handler.chat(get_conversation(user_id), tools=tools.ALL_TOOLS)

    # Now we have a text response (or hit max iterations)
    final_text = response.text or "I'm having trouble processing that. Can you try again?"

    add_to_conversation(user_id, {"role": "assistant", "content": final_text})
    agent_logger.log_final_response(final_text)
    await update.message.reply_text(final_text)


def run_bot():
    """Start the bot"""
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(CallbackQueryHandler(handle_callback))

    
    # Start the bot
    logger.info("Bot starting with calendar/tasks tools enabled...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


# Store pending actions
pending_actions = {}

async def send_confirmation(update, user_id, action_description, action_data):
    """Send confirmation prompt with buttons"""
    keyboard = [
        [
            InlineKeyboardButton("✅ Confirm", callback_data=f"confirm_{user_id}"),
            InlineKeyboardButton("❌ Cancel", callback_data=f"cancel_{user_id}"),
        ],
        [InlineKeyboardButton("✏️ Change", callback_data=f"edit_{user_id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Store the pending action
    pending_actions[user_id] = action_data

    # Use plain text to avoid markdown parsing issues
    await update.message.reply_text(
        f"📋 Proposed action:\n{action_description}\n\nConfirm?",
        reply_markup=reply_markup
    )


async def handle_callback(update, context):
    """Handle button presses"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user_id = update.effective_user.id
    
    if data.startswith("confirm_"):
        # Execute the pending action
        action = pending_actions.pop(user_id, None)
        if action:
            result = tools.execute_tool(action['tool'], action['args'])
            await query.edit_message_text(f"✅ Done! {result}")
    
    elif data.startswith("cancel_"):
        pending_actions.pop(user_id, None)
        await query.edit_message_text("❌ Cancelled.")
    
    elif data.startswith("edit_"):
        await query.edit_message_text("What would you like to change?")


if __name__ == '__main__':
    run_bot()