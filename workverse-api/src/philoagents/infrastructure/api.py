from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from opik.integrations.langchain import OpikTracer
from pydantic import BaseModel

from philoagents.application.conversation_service.generate_response import (
    get_persona_response,
    get_persona_streaming_response,
)
from philoagents.application.conversation_service.reset_conversation import (
    reset_conversation_state,
)
from philoagents.domain.persona_factory import PersonaFactory

from .opik_utils import configure

configure()

_channel_manager = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _channel_manager

    # Start the multi-channel bus (only active channels are booted)
    from philoagents.infrastructure.channels.manager import ChannelManager

    _channel_manager = ChannelManager(app=app)
    await _channel_manager.start()

    yield

    # Shutdown
    if _channel_manager:
        await _channel_manager.stop()
    opik_tracer = OpikTracer()
    opik_tracer.flush()


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class ChatMessage(BaseModel):
    message: str
    persona_id: str


# ---------------------------------------------------------------------------
# REST endpoint
# ---------------------------------------------------------------------------

@app.post("/chat")
async def chat(chat_message: ChatMessage):
    try:
        factory = PersonaFactory()
        persona = factory.get_persona(chat_message.persona_id)

        response, _ = await get_persona_response(
            messages=chat_message.message,
            persona_id=chat_message.persona_id,
            persona_name=persona.name,
            persona_perspective=persona.perspective,
            persona_style=persona.style,
            persona_context="",
        )
        return {"response": response}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        opik_tracer = OpikTracer()
        opik_tracer.flush()
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# WebSocket streaming endpoint
# ---------------------------------------------------------------------------

@app.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket):
    await websocket.accept()

    try:
        while True:
            data = await websocket.receive_json()

            if "message" not in data or "persona_id" not in data:
                await websocket.send_json(
                    {
                        "error": "Invalid message format. Required fields: 'message' and 'persona_id'"
                    }
                )
                continue

            try:
                factory = PersonaFactory()
                persona = factory.get_persona(data["persona_id"])

                response_stream = get_persona_streaming_response(
                    messages=data["message"],
                    persona_id=data["persona_id"],
                    persona_name=persona.name,
                    persona_perspective=persona.perspective,
                    persona_style=persona.style,
                    persona_context="",
                )

                await websocket.send_json({"streaming": True})

                full_response = ""
                async for chunk in response_stream:
                    full_response += chunk
                    await websocket.send_json({"chunk": chunk})

                await websocket.send_json(
                    {"response": full_response, "streaming": False}
                )

            except ValueError as e:
                await websocket.send_json({"error": str(e)})
            except Exception as e:
                opik_tracer = OpikTracer()
                opik_tracer.flush()
                await websocket.send_json({"error": str(e)})

    except WebSocketDisconnect:
        pass


# ---------------------------------------------------------------------------
# Utility endpoints
# ---------------------------------------------------------------------------

@app.get("/personas")
async def list_personas():
    """Return all available persona IDs and their metadata."""
    factory = PersonaFactory()
    return {
        "personas": [
            {
                "id": p.id,
                "name": p.name,
                "role": p.role,
                "expertise": p.expertise,
            }
            for p in factory.list_personas()
        ]
    }


@app.post("/reset-memory")
async def reset_conversation():
    """Reset conversation state by clearing LangGraph checkpoint collections."""
    try:
        result = await reset_conversation_state()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
