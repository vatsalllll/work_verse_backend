import re
import uuid
from typing import Any, AsyncGenerator, Union

from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage
from langgraph.checkpoint.mongodb.aio import AsyncMongoDBSaver
from opik.integrations.langchain import OpikTracer

from philoagents.application.conversation_service.workflow.graph import (
    create_workflow_graph,
)
from philoagents.application.conversation_service.workflow.state import AgentState
from philoagents.config import settings


# Groq/Llama sometimes leaks tool calls as literal text (e.g.
# ``<function=jira_my_tasks>{"status": "To Do"}</function>``) instead of a
# structured tool call. Strip that markup so it never reaches the user.
_TOOL_MARKUP_RE = re.compile(r"<function[^>]*>.*?(?:</function>|$)", re.DOTALL)
_TOOL_MARKUP_START = "<function"
_TOOL_MARKUP_END = "</function>"


def _strip_tool_markup(text: str) -> str:
    """Remove leaked text-form tool-call markup from a complete message."""
    return _TOOL_MARKUP_RE.sub("", text).strip()


def _hold_partial_marker(buffer: str) -> tuple[str, str]:
    """Split ``buffer`` into (emit, hold) where ``hold`` is a trailing partial
    ``<function`` marker that may still be completed by the next chunk."""
    for i in range(min(len(_TOOL_MARKUP_START) - 1, len(buffer)), 0, -1):
        if buffer.endswith(_TOOL_MARKUP_START[:i]):
            return buffer[:-i], buffer[-i:]
    return buffer, ""


async def _sanitize_stream(
    stream: AsyncGenerator[str, None],
) -> AsyncGenerator[str, None]:
    """Yield chunks with any text-form tool-call markup removed.

    Markup can be split across chunk boundaries, so text from a detected
    ``<function`` marker onward is held back until its ``</function>`` close
    arrives (then dropped) or the stream ends (dangling markup is dropped).
    """
    buffer = ""
    async for chunk in stream:
        if not isinstance(chunk, str) or not chunk:
            continue
        buffer += chunk
        while True:
            start = buffer.find(_TOOL_MARKUP_START)
            if start == -1:
                emit, buffer = _hold_partial_marker(buffer)
                if emit:
                    yield emit
                break
            if start > 0:
                yield buffer[:start]
                buffer = buffer[start:]
            end = buffer.find(_TOOL_MARKUP_END)
            if end == -1:
                break  # markup still streaming in — hold everything
            buffer = buffer[end + len(_TOOL_MARKUP_END):]


def _build_thread_id(
    persona_id: str, user_id: str | None, new_thread: bool
) -> str:
    """Build the LangGraph thread id.

    Including ``user_id`` gives every user a private conversation history with
    each persona.  Without a user (e.g. channel adapters) we fall back to a
    persona-only thread for backward compatibility.
    """
    base = f"{user_id}-{persona_id}" if user_id else persona_id
    return f"{base}-{uuid.uuid4()}" if new_thread else base


async def get_persona_response(
    messages: str | list[str] | list[dict[str, Any]],
    persona_id: str,
    persona_name: str,
    persona_perspective: str,
    persona_style: str,
    persona_context: str,
    new_thread: bool = False,
    user_id: str | None = None,
    user_email: str | None = None,
    user_name: str | None = None,
    persona_responsibilities: str = "",
    user_chats: str = "",
) -> tuple[str, AgentState]:
    """Run a conversation through the workflow graph.

    Args:
        messages:            User message(s) to process.
        persona_id:          Unique identifier — used as the LangGraph thread_id
                             so each persona maintains independent conversation history.
        persona_name:        Display name of the active persona.
        persona_perspective: The persona's subject-matter worldview / expertise.
        persona_style:       Conversational tone and manner.
        persona_context:     Additional retrieved context for this turn (RAG output).
        new_thread:          When True, creates a fresh conversation thread.

    Returns:
        tuple[str, AgentState]: The last AI message content and the final state.
    """
    graph_builder = create_workflow_graph()

    try:
        async with AsyncMongoDBSaver.from_conn_string(
            conn_string=settings.MONGO_URI,
            db_name=settings.MONGO_DB_NAME,
            checkpoint_collection_name=settings.MONGO_STATE_CHECKPOINT_COLLECTION,
            writes_collection_name=settings.MONGO_STATE_WRITES_COLLECTION,
        ) as checkpointer:
            graph = graph_builder.compile(checkpointer=checkpointer)
            opik_tracer = OpikTracer(graph=graph.get_graph(xray=True))

            thread_id = _build_thread_id(persona_id, user_id, new_thread)
            config = {
                "configurable": {
                    "thread_id": thread_id,
                    "user_email": user_email,
                    "user_name": user_name,
                },
                "callbacks": [opik_tracer],
            }
            output_state = await graph.ainvoke(
                input={
                    "messages": __format_messages(messages=messages),
                    "persona_id": persona_id,
                    "persona_name": persona_name,
                    "persona_perspective": persona_perspective,
                    "persona_style": persona_style,
                    "persona_responsibilities": persona_responsibilities,
                    "persona_context": persona_context,
                    "user_chats": user_chats,
                },
                config=config,
            )
        last_message = output_state["messages"][-1]
        return _strip_tool_markup(last_message.content), AgentState(**output_state)
    except Exception as e:
        raise RuntimeError(f"Error running conversation workflow: {str(e)}") from e


async def get_persona_streaming_response(
    messages: str | list[str] | list[dict[str, Any]],
    persona_id: str,
    persona_name: str,
    persona_perspective: str,
    persona_style: str,
    persona_context: str,
    new_thread: bool = False,
    user_id: str | None = None,
    user_email: str | None = None,
    user_name: str | None = None,
    persona_responsibilities: str = "",
    user_chats: str = "",
) -> AsyncGenerator[str, None]:
    """Run a conversation through the workflow graph with streaming response.

    Yields:
        Chunks of the response as they become available.
    """
    graph_builder = create_workflow_graph()

    try:
        async with AsyncMongoDBSaver.from_conn_string(
            conn_string=settings.MONGO_URI,
            db_name=settings.MONGO_DB_NAME,
            checkpoint_collection_name=settings.MONGO_STATE_CHECKPOINT_COLLECTION,
            writes_collection_name=settings.MONGO_STATE_WRITES_COLLECTION,
        ) as checkpointer:
            graph = graph_builder.compile(checkpointer=checkpointer)
            opik_tracer = OpikTracer(graph=graph.get_graph(xray=True))

            thread_id = _build_thread_id(persona_id, user_id, new_thread)
            config = {
                "configurable": {
                    "thread_id": thread_id,
                    "user_email": user_email,
                    "user_name": user_name,
                },
                "callbacks": [opik_tracer],
            }

            raw_stream = (
                chunk[0].content
                async for chunk in graph.astream(
                    input={
                        "messages": __format_messages(messages=messages),
                        "persona_id": persona_id,
                        "persona_name": persona_name,
                        "persona_perspective": persona_perspective,
                        "persona_style": persona_style,
                        "persona_responsibilities": persona_responsibilities,
                        "persona_context": persona_context,
                        "user_chats": user_chats,
                    },
                    config=config,
                    stream_mode="messages",
                )
                if chunk[1]["langgraph_node"] == "conversation_node"
                and isinstance(chunk[0], AIMessageChunk)
            )
            async for text in _sanitize_stream(raw_stream):
                yield text

    except Exception as e:
        raise RuntimeError(
            f"Error running streaming conversation workflow: {str(e)}"
        ) from e


# ---------------------------------------------------------------------------
# Backward-compat aliases (keeps existing code/notebooks working)
# ---------------------------------------------------------------------------

async def get_response(
    messages: str | list[str] | list[dict[str, Any]],
    philosopher_id: str,
    philosopher_name: str,
    philosopher_perspective: str,
    philosopher_style: str,
    philosopher_context: str,
    new_thread: bool = False,
) -> tuple[str, AgentState]:
    return await get_persona_response(
        messages=messages,
        persona_id=philosopher_id,
        persona_name=philosopher_name,
        persona_perspective=philosopher_perspective,
        persona_style=philosopher_style,
        persona_context=philosopher_context,
        new_thread=new_thread,
    )


async def get_streaming_response(
    messages: str | list[str] | list[dict[str, Any]],
    philosopher_id: str,
    philosopher_name: str,
    philosopher_perspective: str,
    philosopher_style: str,
    philosopher_context: str,
    new_thread: bool = False,
) -> AsyncGenerator[str, None]:
    # Must use `yield` so this stays an async generator (not a coroutine returning one)
    async for chunk in get_persona_streaming_response(
        messages=messages,
        persona_id=philosopher_id,
        persona_name=philosopher_name,
        persona_perspective=philosopher_perspective,
        persona_style=philosopher_style,
        persona_context=philosopher_context,
        new_thread=new_thread,
    ):
        yield chunk


def __format_messages(
    messages: Union[str, list[dict[str, Any]]],
) -> list[Union[HumanMessage, AIMessage]]:
    if isinstance(messages, str):
        return [HumanMessage(content=messages)]

    if isinstance(messages, list):
        if not messages:
            return []

        if (
            isinstance(messages[0], dict)
            and "role" in messages[0]
            and "content" in messages[0]
        ):
            result = []
            for msg in messages:
                if msg["role"] == "user":
                    result.append(HumanMessage(content=msg["content"]))
                elif msg["role"] == "assistant":
                    result.append(AIMessage(content=msg["content"]))
            return result

        return [HumanMessage(content=message) for message in messages]

    return []
