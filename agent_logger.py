"""
Agent reasoning logger.
Logs detailed information about LLM requests, responses, and tool executions.
"""

import logging
import re
from datetime import datetime
from typing import Any

# Create a dedicated logger for agent reasoning
agent_logger = logging.getLogger('agent_reasoning')
agent_logger.setLevel(logging.DEBUG)

# File handler - detailed logs go here
file_handler = logging.FileHandler('agent_reasoning.log', encoding='utf-8')
file_handler.setLevel(logging.DEBUG)
file_formatter = logging.Formatter('%(asctime)s\n%(message)s\n' + '='*60 + '\n')
file_handler.setFormatter(file_formatter)
agent_logger.addHandler(file_handler)

# Prevent propagation to root logger (keeps terminal clean)
agent_logger.propagate = False


def log_user_message(user_id: int, message: str):
    """Log incoming user message"""
    agent_logger.debug(
        f"[USER {user_id}]\n"
        f"{message}"
    )


def log_llm_request(messages: list, tools: list = None):
    """Log the request being sent to LLM (handles LangChain messages)"""
    msg_summary = []
    for m in messages[-5:]:  # Last 5 messages for context
        # Handle both LangChain messages and dicts
        if hasattr(m, 'type'):  # LangChain message
            role = m.type  # 'human', 'ai', 'system', 'tool'
            content = str(m.content)[:200] if m.content else ''
        else:  # dict format
            role = m.get('role', 'unknown')
            content = str(m.get('content', ''))[:200]
        msg_summary.append(f"  [{role}]: {content}...")

    # Handle LangChain tools (have .name attribute) or dict tools
    tool_names = []
    for t in (tools or []):
        if hasattr(t, 'name'):
            tool_names.append(t.name)
        elif isinstance(t, dict):
            tool_names.append(t.get('function', {}).get('name', 'unknown'))

    agent_logger.debug(
        f"[LLM REQUEST]\n"
        f"Messages ({len(messages)} total, showing last 5):\n" +
        "\n".join(msg_summary) +
        f"\n\nAvailable tools: {tool_names}"
    )


def log_llm_response(text: str, tool_calls: list, thinking: str = None):
    """Log LLM response including any reasoning (handles LangChain tool_calls)"""
    tool_info = ""
    if tool_calls:
        tool_info = "\n\nTool calls:\n"
        for tc in tool_calls:
            # LangChain format: {id, name, args}
            # Old format: {id, type, function: {name, arguments}}
            if 'name' in tc:
                name = tc.get('name')
                args = tc.get('args', {})
            else:
                name = tc.get('function', {}).get('name', 'unknown')
                args = tc.get('function', {}).get('arguments', {})
            tool_info += f"  - {name}: {args}\n"

    thinking_section = ""
    if thinking:
        thinking_section = f"\n\n[THINKING/REASONING]\n{thinking}\n"

    agent_logger.debug(
        f"[LLM RESPONSE]{thinking_section}\n"
        f"[OUTPUT]\n{text or '(no text, tool call only)'}"
        f"{tool_info}"
    )


def log_tool_execution(tool_name: str, args: Any, result: Any):
    """Log tool execution and result"""
    result_str = str(result)
    if len(result_str) > 500:
        result_str = result_str[:500] + "... (truncated)"

    agent_logger.debug(
        f"[TOOL EXECUTION]\n"
        f"Tool: {tool_name}\n"
        f"Args: {args}\n"
        f"Result: {result_str}"
    )


def log_final_response(response: str):
    """Log the final response sent to user"""
    agent_logger.debug(
        f"[FINAL RESPONSE TO USER]\n"
        f"{response}"
    )


def extract_thinking(text: str) -> tuple[str | None, str]:
    """
    Extract <think>...</think> content from qwen3 responses.
    Returns (thinking_content, remaining_text)
    """
    think_pattern = r'<think>(.*?)</think>'
    match = re.search(think_pattern, text, re.DOTALL)

    if match:
        thinking = match.group(1).strip()
        remaining = re.sub(think_pattern, '', text, flags=re.DOTALL).strip()
        return thinking, remaining

    return None, text
