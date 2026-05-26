from langgraph.graph import MessagesState


class AgentState(MessagesState):
    """State for the LangGraph workflow.

    Tracks the information required to maintain a coherent, persona-grounded
    conversation between an NPC and the user.

    Attributes:
        persona_context:     Retrieved knowledge-base context for the current turn.
        persona_name:        Display name of the active persona.
        persona_perspective: The persona's subject-matter worldview / expertise.
        persona_style:       Conversational tone and manner.
        summary:             Rolling conversation summary used to reduce token usage.
    """

    persona_context: str
    persona_name: str
    persona_perspective: str
    persona_style: str
    summary: str


# Backward-compat alias so any code that still imports PhilosopherState keeps working.
PhilosopherState = AgentState


def state_to_str(state: AgentState) -> str:
    if "summary" in state and bool(state["summary"]):
        conversation = state["summary"]
    elif "messages" in state and bool(state["messages"]):
        conversation = state["messages"]
    else:
        conversation = ""

    return (
        f"AgentState("
        f"persona_name={state['persona_name']}, "
        f"persona_perspective={state['persona_perspective']}, "
        f"persona_style={state['persona_style']}, "
        f"persona_context={state['persona_context']}, "
        f"conversation={conversation})"
    )
