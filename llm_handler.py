import logging
from typing import List, Dict, Any, Optional
from langchain_ollama import ChatOllama
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from datetime import datetime

from config import OLLAMA_MODEL
import agent_logger

logger = logging.getLogger(__name__)

_llm = ChatOllama(
    model=OLLAMA_MODEL,
    temperature=0,
    reasoning=True
)


SYSTEM_PROMPT = f"""You're Ariel's personal assistant. Your job is to help them manage their calendar and tasks, and help them decide what to do next.

Current date and time: {datetime.now().strftime('%Y-%m-%d %H:%M')}

You have access to tools to read their calendar and tasks. Use READ tools when:
- The user asks about their schedule, calendar, or events
- The user asks what they should do
- The user asks about their tasks or todos

For any WRITE operations (create/edit/delete events or tasks), you MUST use the propose_action tool. This will ask the user for confirmation before executing. Never try to modify data without using propose_action first.

Be conversational, helpful, and concise. Don't be overly formal or robotic."""





def _to_lc_messages(messages: List[Dict[str, str]]):
    """Convert your dict messages -> LangChain messages."""
    out = []
    for m in messages:
        role = m.get("role")
        content = m.get("content", "")
        if role == "system":
            out.append(SystemMessage(content=content))
        elif role == "user":
            out.append(HumanMessage(content=content))
        elif role == "assistant":
            out.append(AIMessage(content=content))
        elif role == "tool":
            # if you have tool messages, you should include tool_call_id in your dict if possible
            # fallback: use a dummy id
            out.append(ToolMessage(content=content, tool_call_id=m.get("tool_call_id", "tool_call")))
        else:
            out.append(HumanMessage(content=content))
    return out





class LLMResponse:
    """Structured response from LLM"""
    def __init__(self, text: str, tool_calls: List[Dict] = None):
        self.text = text
        self.tool_calls = tool_calls or []
    
    def has_tool_calls(self) -> bool:
        return len(self.tool_calls) > 0


def chat(messages: List[Dict[str, str]], tools: List[Dict] = None) -> LLMResponse:
    try:
        # Ensure system prompt
        if not messages or messages[0].get("role") != "system":
            messages = [{"role": "system", "content": SYSTEM_PROMPT}] + messages

        lc_messages = _to_lc_messages(messages)

        # If you want Ollama tool-calling, bind tools
        llm = _llm
        if tools:
            llm = llm.bind_tools(tools)

        logger.info(f"Calling LLM with {len(lc_messages)} messages")

        # Log detailed request to file
        agent_logger.log_llm_request(messages, tools)

        ai_msg = llm.invoke(lc_messages)
        thinking = (ai_msg.additional_kwargs or {}).get("reasoning_content")  # <-- key


        text = ai_msg.content or ""
        tool_calls = getattr(ai_msg, "tool_calls", []) or []
        
        if not thinking:
            # Extract thinking/reasoning from qwen3 responses
            thinking, text = agent_logger.extract_thinking(text)

        # Log detailed response to file
        agent_logger.log_llm_response(text, tool_calls, thinking)

        if tool_calls:
            logger.info(f"LLM wants to call {len(tool_calls)} tool(s)")
            for tc in tool_calls:
                logger.info(f"  - {tc.get('name')}")

        # Convert tool_calls to your prior format
        normalized_tool_calls = []
        for tc in tool_calls:
            normalized_tool_calls.append({
                "id": tc.get("id"),
                "type": "function",
                "function": {
                    "name": tc.get("name"),
                    "arguments": tc.get("args", {}),
                }
            })

        return LLMResponse(text=text, tool_calls=normalized_tool_calls)

    except Exception as e:
        logger.exception(f"Error calling LLM: {e}")
        return LLMResponse(text="Sorry, I had trouble processing that. Can you try again?")


def format_tool_result(tool_name: str, result: Any, tool_call_id: Optional[str] = None) -> Dict[str, str]:
    import json
    return {
        "role": "tool",
        "content": json.dumps(result) if not isinstance(result, str) else result,
        # helps LangChain ToolMessage correlate tool outputs
        "tool_call_id": tool_call_id or tool_name,
    }