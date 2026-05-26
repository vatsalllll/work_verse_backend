"""Slack channel adapter — Socket Mode via slack-bolt async.

Requires: ``pip install slack-bolt``

Socket Mode keeps a persistent WebSocket to Slack so no public inbound
webhook URL is needed — ideal for local development and firewalled servers.

Session key format: ``slack:<channel_id>``
"""

import asyncio

from loguru import logger

from philoagents.infrastructure.messaging import MessageBus

from .base import BaseChannel

try:
    from slack_bolt.async_app import AsyncApp
    from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler

    _SLACK_AVAILABLE = True
except ImportError:  # pragma: no cover
    _SLACK_AVAILABLE = False


class SlackChannel(BaseChannel):
    prefix = "slack"

    def __init__(
        self,
        bot_token: str,
        app_token: str,
        bus: MessageBus,
        default_persona_id: str = "default",
    ) -> None:
        super().__init__(bus=bus, default_persona_id=default_persona_id)
        if not _SLACK_AVAILABLE:
            raise ImportError("slack-bolt is required: pip install slack-bolt")

        self._bot_token = bot_token
        self._app_token = app_token
        self._handler: "AsyncSocketModeHandler | None" = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        app = AsyncApp(token=self._bot_token)

        @app.event("message")
        async def handle_message(event: dict, say):
            # Ignore bot messages and sub-types (edits, deletes, etc.)
            if event.get("bot_id") or event.get("subtype"):
                return

            text = event.get("text", "").strip()
            channel_id = event.get("channel", "")
            if not text or not channel_id:
                return

            if text.startswith("/persona "):
                persona_id = text.split(maxsplit=1)[1].strip()
                await self._push_inbound(chat_id=channel_id, text="", persona_id=persona_id, is_system=True)
                await say(f"Switched to persona: *{persona_id}*")
                return

            await self._push_inbound(chat_id=channel_id, text=text)

        self._handler = AsyncSocketModeHandler(app, self._app_token)
        logger.info("SlackChannel starting Socket Mode connection")
        asyncio.create_task(self._handler.start_async())

    async def stop(self) -> None:
        if self._handler:
            await self._handler.close_async()
        logger.info("SlackChannel stopped")

    # ------------------------------------------------------------------
    # Sending
    # ------------------------------------------------------------------

    async def send_message(self, chat_id: str, text: str) -> None:
        if self._handler is None:
            return
        # slack-bolt's underlying client is available via handler.app.client
        await self._handler.app.client.chat_postMessage(channel=chat_id, text=text)
