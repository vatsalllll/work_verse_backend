from functools import lru_cache

from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import tools_condition

from philoagents.application.conversation_service.workflow.edges import (
    route_after_tools,
    should_summarize_conversation,
)
from philoagents.application.conversation_service.workflow.nodes import (
    conversation_node,
    summarize_conversation_node,
    tool_node,
    summarize_context_node,
    connector_node,
)
from philoagents.application.conversation_service.workflow.state import AgentState


@lru_cache(maxsize=1)
def create_workflow_graph():
    graph_builder = StateGraph(AgentState)

    # Add all nodes
    graph_builder.add_node("conversation_node", conversation_node)
    graph_builder.add_node("tools", tool_node)
    graph_builder.add_node("summarize_conversation_node", summarize_conversation_node)
    graph_builder.add_node("summarize_context_node", summarize_context_node)
    graph_builder.add_node("connector_node", connector_node)

    # Define the flow
    graph_builder.add_edge(START, "conversation_node")
    graph_builder.add_conditional_edges(
        "conversation_node",
        tools_condition,
        {
            "tools": "tools",
            END: "connector_node"
        }
    )
    # After a tool runs, compact results (Jira) go straight back to the persona;
    # large knowledge-base retrievals are summarised first.
    graph_builder.add_conditional_edges(
        "tools",
        route_after_tools,
        {
            "summarize_context_node": "summarize_context_node",
            "conversation_node": "conversation_node",
        },
    )
    graph_builder.add_edge("summarize_context_node", "conversation_node")
    graph_builder.add_conditional_edges("connector_node", should_summarize_conversation)
    graph_builder.add_edge("summarize_conversation_node", END)

    return graph_builder

# Compiled without a checkpointer. Used for LangGraph Studio
graph = create_workflow_graph().compile()
