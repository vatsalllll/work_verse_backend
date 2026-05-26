from pydantic import BaseModel


class Persona(BaseModel):
    """Represents a workverse NPC character that the agent can embody.

    This replaces the Philosopher model for the general persona use-case.
    The fields map 1-to-1 to the LangGraph AgentState fields so no
    translation layer is needed at the workflow boundary.

    Attributes:
        id:          Unique slug used in API requests and session routing.
        name:        Display name shown to users.
        role:        Job title / archetype (e.g. "Senior Software Engineer").
        perspective: The persona's worldview or area of subject-matter expertise,
                     used to ground the LLM's responses.
        style:       Conversational tone and manner (terse, empathetic, Socratic…).
        expertise:   List of topic domains the persona is knowledgeable about.
    """

    id: str
    name: str
    role: str
    perspective: str
    style: str
    expertise: list[str] = []
