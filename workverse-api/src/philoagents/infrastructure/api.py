from contextlib import asynccontextmanager

from fastapi import (
    Depends,
    FastAPI,
    Header,
    HTTPException,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from opik.integrations.langchain import OpikTracer
from pydantic import BaseModel, EmailStr

from philoagents.application.auth_service import AuthError, AuthService, UserRepository
from philoagents.application.conversation_service.generate_response import (
    get_persona_response,
    get_persona_streaming_response,
)
from philoagents.application.conversation_service.reset_conversation import (
    reset_conversation_state,
)
from philoagents.application.messaging_service import get_messaging_service
from philoagents.config import settings
from philoagents.domain.persona_factory import PersonaFactory
from philoagents.infrastructure import oauth
from philoagents.infrastructure.security import (
    create_access_token,
    create_state_token,
    decode_access_token,
    verify_state_token,
)

from .opik_utils import configure

configure()

_channel_manager = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _channel_manager

    # Ensure the users collection has its unique email index
    try:
        UserRepository().ensure_indexes()
        get_messaging_service().ensure_indexes()
        if settings.DEMO_MODE:
            AuthService().seed_demo_users()
            get_messaging_service().seed_demo_conversations()
    except Exception as e:  # non-fatal: log and continue
        from loguru import logger

        logger.warning(f"Could not ensure indexes / seed demo users: {e}")

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


class RegisterRequest(BaseModel):
    name: str
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


# ---------------------------------------------------------------------------
# Auth dependency
# ---------------------------------------------------------------------------

def get_current_user(authorization: str | None = Header(default=None)) -> dict:
    """FastAPI dependency: validate the Bearer token and return its payload.

    The payload contains ``sub`` (user id), ``email`` and ``name``.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid token.")
    token = authorization.split(" ", 1)[1].strip()
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token.")
    return payload


# ---------------------------------------------------------------------------
# Auth endpoints
# ---------------------------------------------------------------------------

@app.post("/auth/register")
async def register(req: RegisterRequest):
    if len(req.password) < 6:
        raise HTTPException(
            status_code=400, detail="Password must be at least 6 characters."
        )
    try:
        user = AuthService().register(req.name, req.email, req.password)
    except AuthError as e:
        raise HTTPException(status_code=409, detail=str(e))
    token = create_access_token(user.id, user.email, user.name)
    return {"token": token, "user": user.public_dict()}


@app.post("/auth/login")
async def login(req: LoginRequest):
    try:
        user = AuthService().login(req.email, req.password)
    except AuthError as e:
        raise HTTPException(status_code=401, detail=str(e))
    token = create_access_token(user.id, user.email, user.name)
    return {"token": token, "user": user.public_dict()}


class DemoLoginRequest(BaseModel):
    email: EmailStr


@app.get("/auth/demo-users")
async def demo_users():
    if not settings.DEMO_MODE:
        raise HTTPException(status_code=404, detail="Demo mode is disabled.")
    return {"users": AuthService().list_demo_users()}


@app.post("/auth/demo-login")
async def demo_login(req: DemoLoginRequest):
    if not settings.DEMO_MODE:
        raise HTTPException(status_code=404, detail="Demo mode is disabled.")
    try:
        user = AuthService().demo_login(req.email)
    except AuthError as e:
        raise HTTPException(status_code=400, detail=str(e))
    token = create_access_token(user.id, user.email, user.name)
    return {"token": token, "user": user.public_dict()}


@app.get("/auth/me")
async def me(current_user: dict = Depends(get_current_user)):
    return {
        "user": {
            "id": current_user["sub"],
            "email": current_user.get("email"),
            "name": current_user.get("name"),
        }
    }


# ---------------------------------------------------------------------------
# OAuth endpoints (Google / Slack) — Phase B/C
# ---------------------------------------------------------------------------

def _frontend_redirect(*, token: str | None = None, error: str | None = None) -> RedirectResponse:
    """Build a redirect back to the game with a token or an error message."""
    if token:
        return RedirectResponse(url=f"{settings.FRONTEND_URL}/?token={token}")
    return RedirectResponse(url=f"{settings.FRONTEND_URL}/?auth_error={error}")


@app.get("/auth/{provider}/login")
async def oauth_login(provider: str):
    if not oauth.is_supported(provider):
        raise HTTPException(status_code=404, detail="Unknown auth provider.")
    if not oauth.is_configured(provider):
        return _frontend_redirect(error=f"{provider}_not_configured")
    state = create_state_token(provider)
    return RedirectResponse(url=oauth.build_authorize_url(provider, state))


@app.get("/auth/{provider}/callback")
async def oauth_callback(
    provider: str,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
):
    if not oauth.is_supported(provider):
        raise HTTPException(status_code=404, detail="Unknown auth provider.")
    if error or not code:
        return _frontend_redirect(error=f"{provider}_login_failed")
    if not state or not verify_state_token(state, provider):
        return _frontend_redirect(error="invalid_state")

    try:
        profile = await oauth.exchange_code_for_userinfo(provider, code)
        user = AuthService().get_or_create_oauth_user(
            name=profile["name"], email=profile["email"], provider=provider
        )
        token = create_access_token(user.id, user.email, user.name)
        return _frontend_redirect(token=token)
    except Exception as e:
        from loguru import logger

        logger.error(f"{provider} OAuth callback failed: {e}")
        return _frontend_redirect(error=f"{provider}_login_failed")


# ---------------------------------------------------------------------------
# Presence + human-to-human direct messaging
# ---------------------------------------------------------------------------

class SendMessageRequest(BaseModel):
    to_user_id: str
    text: str


@app.post("/presence/ping")
async def presence_ping(current_user: dict = Depends(get_current_user)):
    get_messaging_service().ping(current_user["sub"])
    return {"ok": True}


@app.get("/presence/online")
async def presence_online(current_user: dict = Depends(get_current_user)):
    return {"users": get_messaging_service().online_users(current_user["sub"])}


@app.get("/users")
async def list_users(current_user: dict = Depends(get_current_user)):
    """Workspace directory — everyone, with an online flag. Message anyone."""
    return {"users": get_messaging_service().directory(current_user["sub"])}


@app.post("/dm/send")
async def dm_send(
    req: SendMessageRequest, current_user: dict = Depends(get_current_user)
):
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty.")
    get_messaging_service().send(
        current_user["sub"], current_user.get("name") or "", req.to_user_id, req.text
    )
    return {"ok": True}


@app.get("/dm/with/{other_user_id}")
async def dm_with(
    other_user_id: str, current_user: dict = Depends(get_current_user)
):
    return {
        "messages": get_messaging_service().conversation(
            current_user["sub"], other_user_id
        )
    }


@app.get("/dm/unread")
async def dm_unread(current_user: dict = Depends(get_current_user)):
    return {"unread": get_messaging_service().unread_summary(current_user["sub"])}


# ---------------------------------------------------------------------------
# REST endpoint
# ---------------------------------------------------------------------------

@app.post("/chat")
async def chat(chat_message: ChatMessage, current_user: dict = Depends(get_current_user)):
    try:
        factory = PersonaFactory()
        persona = factory.get_persona(chat_message.persona_id)

        user_chats = get_messaging_service().build_chat_context_for_user(
            current_user["sub"]
        )

        response, _ = await get_persona_response(
            messages=chat_message.message,
            persona_id=chat_message.persona_id,
            persona_name=persona.name,
            persona_perspective=persona.perspective,
            persona_style=persona.style,
            persona_context="",
            persona_responsibilities=persona.responsibilities,
            user_id=current_user["sub"],
            user_email=current_user.get("email"),
            user_name=current_user.get("name"),
            user_chats=user_chats,
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

    # Browsers cannot set WebSocket headers, so the token arrives as a query
    # param: ws://host/ws/chat?token=<jwt>
    token = websocket.query_params.get("token")
    payload = decode_access_token(token) if token else None
    if not payload:
        await websocket.send_json({"error": "Unauthorized. Please log in again."})
        await websocket.close(code=4401)
        return
    user_id = payload["sub"]
    user_email = payload.get("email")
    user_name = payload.get("name")

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

                user_chats = get_messaging_service().build_chat_context_for_user(
                    user_id
                )

                response_stream = get_persona_streaming_response(
                    messages=data["message"],
                    persona_id=data["persona_id"],
                    persona_name=persona.name,
                    persona_perspective=persona.perspective,
                    persona_style=persona.style,
                    persona_context="",
                    persona_responsibilities=persona.responsibilities,
                    user_id=user_id,
                    user_email=user_email,
                    user_name=user_name,
                    user_chats=user_chats,
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
