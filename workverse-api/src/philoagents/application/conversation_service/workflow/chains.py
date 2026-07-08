from functools import lru_cache

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_groq import ChatGroq

from philoagents.application.conversation_service.workflow.tools import get_tools_for
from philoagents.config import settings
from philoagents.domain.persona_factory import PersonaFactory
from philoagents.domain.prompts import (
    CONTEXT_SUMMARY_PROMPT,
    EXTEND_SUMMARY_PROMPT,
    PERSONA_CHARACTER_CARD,
    SUMMARY_PROMPT,
)


def get_chat_model(temperature: float = 0.7, model_name: str = settings.GROQ_LLM_MODEL) -> ChatGroq:
    return ChatGroq(
        api_key=settings.GROQ_API_KEY,
        model_name=model_name,
        temperature=temperature,
    )


def _persona_tool_slugs(persona_id: str) -> list[str]:
    try:
        return PersonaFactory().get_persona(persona_id).tools
    except ValueError:
        return []


@lru_cache(maxsize=None)
def get_persona_response_chain(persona_id: str | None = None):
    """Build the conversation chain, binding only the tools this persona may use.

    Cached per ``persona_id`` so each role keeps its own tool-bound model.
    """
    model = get_chat_model()
    persona_tools = get_tools_for(_persona_tool_slugs(persona_id)) if persona_id else []
    if persona_tools:
        model = model.bind_tools(persona_tools)

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", PERSONA_CHARACTER_CARD.prompt),
            MessagesPlaceholder(variable_name="messages"),
        ],
        template_format="jinja2",
    )

    return prompt | model


@lru_cache(maxsize=None)
def get_persona_tools_summary(persona_id: str | None = None) -> str:
    """Human-readable list of the persona's tools, for the system prompt."""
    persona_tools = get_tools_for(_persona_tool_slugs(persona_id)) if persona_id else []
    if not persona_tools:
        return "None. Answer from your own knowledge and never invent system data."
    return "\n".join(f"- {t.name}: {t.description}" for t in persona_tools)


def get_conversation_summary_chain(summary: str = ""):
    model = get_chat_model(model_name=settings.GROQ_LLM_MODEL_CONTEXT_SUMMARY)

    summary_message = EXTEND_SUMMARY_PROMPT if summary else SUMMARY_PROMPT

    prompt = ChatPromptTemplate.from_messages(
        [
            MessagesPlaceholder(variable_name="messages"),
            ("human", summary_message.prompt),
        ],
        template_format="jinja2",
    )

    return prompt | model


def get_context_summary_chain():
    model = get_chat_model(model_name=settings.GROQ_LLM_MODEL_CONTEXT_SUMMARY)
    prompt = ChatPromptTemplate.from_messages(
        [
            ("human", CONTEXT_SUMMARY_PROMPT.prompt),
        ],
        template_format="jinja2",
    )

    return prompt | model
