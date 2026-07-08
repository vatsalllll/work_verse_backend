from langchain_core.messages import RemoveMessage
from langchain_core.runnables import RunnableConfig
from langgraph.prebuilt import ToolNode

from philoagents.application.conversation_service.workflow.chains import (
    get_context_summary_chain,
    get_conversation_summary_chain,
    get_persona_response_chain,
    get_persona_tools_summary,
)
from philoagents.application.conversation_service.workflow.state import AgentState
from philoagents.application.conversation_service.workflow.tools import all_tools
from philoagents.config import settings

# Single ToolNode holding every registered tool; it only executes whatever the
# model actually called (which is gated per-persona at bind time).
tool_node = ToolNode(all_tools())
# Backward-compat alias (the graph historically named this node's executor).
retriever_node = tool_node


async def conversation_node(state: AgentState, config: RunnableConfig):
    summary = state.get("summary", "")
    persona_id = state.get("persona_id")
    conversation_chain = get_persona_response_chain(persona_id)

    response = await conversation_chain.ainvoke(
        {
            "messages": state["messages"],
            "persona_context": state["persona_context"],
            "persona_name": state["persona_name"],
            "persona_perspective": state["persona_perspective"],
            "persona_style": state["persona_style"],
            "persona_responsibilities": state.get("persona_responsibilities", ""),
            "user_chats": state.get("user_chats", "") or "No direct messages yet.",
            "available_tools": get_persona_tools_summary(persona_id),
            "summary": summary,
        },
        config,
    )

    return {"messages": response}


async def summarize_conversation_node(state: AgentState):
    summary = state.get("summary", "")
    summary_chain = get_conversation_summary_chain(summary)

    response = await summary_chain.ainvoke(
        {
            "messages": state["messages"],
            "persona_name": state["persona_name"],
            "summary": summary,
        }
    )

    delete_messages = [
        RemoveMessage(id=m.id)
        for m in state["messages"][: -settings.TOTAL_MESSAGES_AFTER_SUMMARY]
    ]
    return {"summary": response.content, "messages": delete_messages}


async def summarize_context_node(state: AgentState):
    context_summary_chain = get_context_summary_chain()

    response = await context_summary_chain.ainvoke(
        {
            "context": state["messages"][-1].content,
        }
    )
    state["messages"][-1].content = response.content

    return {}


async def connector_node(_state: AgentState):
    return {}
