import os
from dotenv import load_dotenv

load_dotenv()

# Telegram
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

# Ollama
OLLAMA_HOST = os.getenv('OLLAMA_HOST', 'http://localhost:11434')
OLLAMA_MODEL = os.getenv('OLLAMA_MODEL', 'qwen3:latest')

# Conversation settings
MAX_HISTORY_MESSAGES = 20  # Keep last 20 messages for context

# Database
DATABASE_PATH = os.getenv('DATABASE_PATH', 'proactive.db')

# Proactive features
DEFAULT_TIMEZONE = os.getenv('DEFAULT_TIMEZONE', 'Asia/Jerusalem')
EVENT_REMINDER_MINUTES = int(os.getenv('EVENT_REMINDER_MINUTES', '30'))
OVERDUE_CHECK_INTERVAL_MINUTES = int(os.getenv('OVERDUE_CHECK_INTERVAL_MINUTES', '60'))