# Personal Assistant V4

A Telegram bot that uses local LLMs (via Ollama) to manage Google Calendar and Tasks through natural conversation.

## What it does

Talk to the bot in Telegram using natural language and it'll handle your calendar and tasks:
- "Schedule a meeting tomorrow at 2pm"
- "What's on my calendar today?"
- "Add task: buy groceries"
- "Mark the report task as done"

## Setup

1. **Install requirements**
```bash
pip install -r requirements.txt
```

2. **Get Ollama running**
```bash
ollama pull qwen3:8b
# or llama3.1:8b, mistral:7b
```

3. **Google API credentials**
   - Create a project in Google Cloud Console
   - Enable Calendar and Tasks APIs
   - Download OAuth2 credentials
   - Put the JSON file in the project folder

4. **Configure**
   - Set `TELEGRAM_BOT_TOKEN` in your environment
   - Update paths in `config.py` if needed

5. **Run it**
```bash
python main.py
```

## Model notes

I've tested with:
- **qwen3:8b** - Best reasoning, what I'm using now
- **llama3.1:8b** - Solid all-around
- **mistral:7b** - Faster but less reliable with function calls

Function calling can be finicky - some models need more prompt tweaking than others. Check `test_models.py` to compare.

## Files

- `main.py` - Entry point
- `bot.py` - Telegram handlers
- `llm_handler.py` - Ollama integration + function calling
- `google_api.py` - Calendar/Tasks API wrapper
- `tools.py` - Function definitions for the LLM
- `session.py` - Conversation context
- `scheduler.py` - Background tasks
- `proactive.py` - Reminder notifications

## Known issues

- Function call reliability varies by model
- Sometimes needs multiple tries to parse tool calls correctly
- Prompt engineering is ongoing

## Todo

- Better date parsing
- More tool integrations
- Multi-user support
