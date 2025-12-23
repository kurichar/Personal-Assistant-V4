"""
LLM handler using LangChain with Ollama.
Uses LangChain message format throughout - no conversions needed.
"""

import logging
from typing import List, Optional
from langchain_ollama import ChatOllama
from langchain_core.messages import (
    BaseMessage,
    SystemMessage,
    HumanMessage,
    AIMessage,
    ToolMessage,
)
from datetime import datetime

from config import OLLAMA_MODEL
import agent_logger

logger = logging.getLogger(__name__)

# Initialize the LLM with reasoning enabled
_llm = ChatOllama(
    model=OLLAMA_MODEL,
    temperature=0,
    reasoning=True,
    timeout=120,  # 2 minute timeout to prevent infinite hangs
)

# System prompt template - {current_datetime} is replaced on each call
SYSTEM_PROMPT_TEMPLATE = """You are Ariel's personal assistant. Help manage their calendar and tasks.

Current date and time: {current_datetime}

## Guidelines

**Clarify before proposing:**
- If details are ambiguous or missing (time, duration, specific date), ASK the user first
- Don't assume times - ask "What time?" if not specified
- Don't guess durations - ask if it matters
- Example: "Schedule a meeting tomorrow" → Ask "What time would you like it?"

**Read before write:**
- ALWAYS call get_tasks or get_calendar_events BEFORE editing/deleting
- This ensures you have the correct, current IDs
- Never use IDs from memory - always fetch fresh

**Proposals:**
- Use propose_* tools for any create/edit/delete/complete operation
- Include all relevant details the user provided
- User will confirm before execution

**After actions complete:**
- Acknowledge what was done naturally
- Offer to help with related tasks if appropriate

Be conversational and helpful."""


def get_system_message() -> SystemMessage:
    """Get system message with current datetime"""
    return SystemMessage(content=SYSTEM_PROMPT_TEMPLATE.format(
        current_datetime=datetime.now().strftime('%Y-%m-%d %H:%M')
    ))


# Enable streaming of reasoning to terminal
STREAM_REASONING = True


def chat(messages: List[BaseMessage], tools: list = None) -> AIMessage:
    """
    Send messages to LLM and get response.
    If STREAM_REASONING is True, streams reasoning to terminal in real-time.

    Args:
        messages: List of LangChain messages (HumanMessage, AIMessage, ToolMessage)
                  SystemMessage is NOT expected - we prepend fresh one each call
        tools: List of LangChain tools (@tool decorated functions)

    Returns:
        AIMessage with response text and/or tool_calls
    """
    try:        # Always prepend fresh system message with current time
        # Don't store system message in conversation - it's added fresh each call
        messages = [get_system_message()] + list(messages)
        
        # Warn if conversation is getting very large
        if len(messages) > 30:
            logger.warning(f"Conversation has {len(messages)} messages - consider trimming history if responses are slow")

        # Bind tools if provided
        llm = _llm
        if tools:
            llm = llm.bind_tools(tools)

        logger.info(f"Calling LLM with {len(messages)} messages")

        # Log the request
        agent_logger.log_llm_request(messages, tools)

        if STREAM_REASONING:
            # Stream the response to see reasoning in real-time
            ai_msg = _stream_with_reasoning(llm, messages)
        else:
            # Regular invoke
            ai_msg: AIMessage = llm.invoke(messages)

        # Extract reasoning if available
        thinking = (ai_msg.additional_kwargs or {}).get("reasoning_content")
        text = ai_msg.content or ""

        # Fallback: extract thinking from response text if not in kwargs
        if not thinking:
            thinking, text = agent_logger.extract_thinking(text)
            # Update the message content with cleaned text
            ai_msg.content = text

        # Log the response
        agent_logger.log_llm_response(text, ai_msg.tool_calls, thinking)

        if ai_msg.tool_calls:
            logger.info(f"LLM wants to call {len(ai_msg.tool_calls)} tool(s)")
            for tc in ai_msg.tool_calls:
                logger.info(f"  - {tc.get('name')}")

        return ai_msg

    except Exception as e:
        logger.exception(f"Error calling LLM: {e}")
        # Return an error message
        return AIMessage(content="Sorry, I had trouble processing that. Can you try again?")


def _stream_with_reasoning(llm, messages: List[BaseMessage]) -> AIMessage:
    """
    Stream LLM response and print reasoning to terminal in real-time.
    Returns the complete AIMessage when done.
    """
    import sys

    print("\n" + "=" * 50)
    print("REASONING:")
    print("-" * 50)

    # Collect the full response
    full_content = ""
    full_reasoning = ""
    tool_calls = []
    in_reasoning = False

    for chunk in llm.stream(messages):
        # Handle reasoning content (from additional_kwargs)
        if hasattr(chunk, 'additional_kwargs'):
            reasoning_chunk = chunk.additional_kwargs.get('reasoning_content', '')
            if reasoning_chunk:
                # Print reasoning in real-time (yellow color)
                print(f"\033[33m{reasoning_chunk}\033[0m", end="", flush=True)
                full_reasoning += reasoning_chunk
                in_reasoning = True

        # Handle regular content
        if chunk.content:
            if in_reasoning:
                # First content after reasoning - print separator
                print("\n" + "-" * 50)
                print("RESPONSE:")
                in_reasoning = False
            # Print response content (green color)
            print(f"\033[32m{chunk.content}\033[0m", end="", flush=True)
            full_content += chunk.content        # Collect tool calls
        if hasattr(chunk, 'tool_calls') and chunk.tool_calls:
            tool_calls.extend(chunk.tool_calls)
        if hasattr(chunk, 'tool_call_chunks') and chunk.tool_call_chunks:
            # Handle streaming tool calls (need to merge chunks)
            for tc_chunk in chunk.tool_call_chunks:
                # Find or create the tool call
                existing = next((tc for tc in tool_calls if tc.get('index') == tc_chunk.get('index')), None)
                if existing:
                    # Merge args - handle both string and dict types
                    if tc_chunk.get('args'):
                        chunk_args = tc_chunk['args']
                        existing_args = existing.get('args', '')
                        # If already a dict, keep it; if string, concatenate
                        if isinstance(existing_args, dict):
                            existing['args'] = existing_args
                        elif isinstance(chunk_args, dict):
                            existing['args'] = chunk_args
                        else:
                            existing['args'] = existing_args + chunk_args
                else:
                    tool_calls.append({
                        'index': tc_chunk.get('index'),
                        'id': tc_chunk.get('id', ''),
                        'name': tc_chunk.get('name', ''),
                        'args': tc_chunk.get('args', '')
                    })

    print("\n" + "=" * 50 + "\n")

    # Parse tool call args from string to dict
    import json
    parsed_tool_calls = []
    for tc in tool_calls:
        if isinstance(tc.get('args'), str) and tc['args']:
            try:
                tc['args'] = json.loads(tc['args'])
            except json.JSONDecodeError:
                pass
        if tc.get('name'):  # Only include if it has a name
            parsed_tool_calls.append({
                'id': tc.get('id', f"call_{len(parsed_tool_calls)}"),
                'name': tc['name'],
                'args': tc.get('args', {})
            })

    # Build the final AIMessage
    return AIMessage(
        content=full_content,
        tool_calls=parsed_tool_calls,
        additional_kwargs={'reasoning_content': full_reasoning} if full_reasoning else {}
    )


def create_tool_message(tool_call_id: str, content: str) -> ToolMessage:
    """
    Create a ToolMessage for a tool result.

    Args:
        tool_call_id: The ID from the tool_call
        content: The result content (will be converted to string if needed)

    Returns:
        ToolMessage ready to add to conversation
    """
    import json
    if not isinstance(content, str):
        content = json.dumps(content)
    return ToolMessage(content=content, tool_call_id=tool_call_id)