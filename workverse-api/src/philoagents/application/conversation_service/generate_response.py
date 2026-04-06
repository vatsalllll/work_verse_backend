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


async def get_persona_response(
    messages: str | list[str] | list[dict[str, Any]],
    persona_id: str,
    persona_name: str,
    persona_perspective: str,
    persona_style: str,
    persona_context: str,
    new_thread: bool = False,
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

            thread_id = (
                persona_id if not new_thread else f"{persona_id}-{uuid.uuid4()}"
            )
            config = {
                "configurable": {"thread_id": thread_id},
                "callbacks": [opik_tracer],
            }
            output_state = await graph.ainvoke(
                input={
                    "messages": __format_messages(messages=messages),
                    "persona_name": persona_name,
                    "persona_perspective": persona_perspective,
                    "persona_style": persona_style,
                    "persona_context": persona_context,
                },
                config=config,
            )
        last_message = output_state["messages"][-1]
        return last_message.content, AgentState(**output_state)
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

            thread_id = (
                persona_id if not new_thread else f"{persona_id}-{uuid.uuid4()}"
            )
            config = {
                "configurable": {"thread_id": thread_id},
                "callbacks": [opik_tracer],
            }

            async for chunk in graph.astream(
                input={
                    "messages": __format_messages(messages=messages),
                    "persona_name": persona_name,
                    "persona_perspective": persona_perspective,
                    "persona_style": persona_style,
                    "persona_context": persona_context,
                },
                config=config,
                stream_mode="messages",
            ):
                if chunk[1]["langgraph_node"] == "conversation_node" and isinstance(
                    chunk[0], AIMessageChunk
                ):
                    yield chunk[0].content

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
