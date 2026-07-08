from typing_extensions import Literal

from langchain_core.messages import ToolMessage
from langgraph.graph import END

from philoagents.application.conversation_service.workflow.state import AgentState
from philoagents.config import settings

# Tools whose (potentially large) output should be compressed by the context
# summariser before returning to the persona. Other tools (e.g. Jira) already
# return compact, structured text and must reach the persona intact.
_SUMMARISE_TOOL_NAMES = {"retrieve_philosopher_context"}


def route_after_tools(
    state: AgentState,
) -> Literal["summarize_context_node", "conversation_node"]:
    """Decide what happens to a tool result.

    Large knowledge-base retrievals are summarised first; compact tool results
    (like Jira issues) go straight back to the persona without being shrunk.
    """
    last = state["messages"][-1]
    name = getattr(last, "name", None) if isinstance(last, ToolMessage) else None
    if name in _SUMMARISE_TOOL_NAMES:
        return "summarize_context_node"
    return "conversation_node"


def should_summarize_conversation(
    state: AgentState,
) -> Literal["summarize_conversation_node", "__end__"]:
    messages = state["messages"]

    if len(messages) > settings.TOTAL_MESSAGES_SUMMARY_TRIGGER:
        return "summarize_conversation_node"

    return END
