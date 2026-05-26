"""Telegram channel adapter — long-polling via aiohttp.

Uses the raw Bot API (no third-party telegram library) so the only extra
dependency is ``aiohttp``, which is already pulled in by ``fastapi[standard]``.

Session key format: ``telegram:<chat_id>``
"""

import asyncio

import aiohttp
from loguru import logger

from philoagents.infrastructure.messaging import MessageBus

from .base import BaseChannel

_API_BASE = "https://api.telegram.org/bot{token}"
_MAX_CHUNK = 4096  # Telegram's hard message-length limit


class TelegramChannel(BaseChannel):
    prefix = "telegram"

    def __init__(self, token: str, bus: MessageBus, default_persona_id: str = "default") -> None:
        super().__init__(bus=bus, default_persona_id=default_persona_id)
        self._token = token
        self._base = _API_BASE.format(token=token)
        self._offset = 0
        self._running = False
        self._session: aiohttp.ClientSession | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        self._running = True
        self._session = aiohttp.ClientSession()
        logger.info("TelegramChannel started — polling for updates")
        await self._poll_loop()

    async def stop(self) -> None:
        self._running = False
        if self._session:
            await self._session.close()
        logger.info("TelegramChannel stopped")

    # ------------------------------------------------------------------
    # Sending
    # ------------------------------------------------------------------

    async def send_message(self, chat_id: str, text: str) -> None:
        """Send a text reply, splitting at Telegram's 4096-char limit."""
        chunks = [text[i : i + _MAX_CHUNK] for i in range(0, len(text), _MAX_CHUNK)]
        for chunk in chunks:
            await self._api("sendMessage", chat_id=int(chat_id), text=chunk)

    # ------------------------------------------------------------------
    # Internal polling loop
    # ------------------------------------------------------------------

    async def _poll_loop(self) -> None:
        while self._running:
            try:
                updates = await self._get_updates()
                for update in updates:
                    self._offset = update["update_id"] + 1
                    await self._handle_update(update)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning(f"TelegramChannel poll error: {exc}")
                await asyncio.sleep(3)

    async def _get_updates(self) -> list[dict]:
        params = {"timeout": 30, "offset": self._offset, "allowed_updates": ["message"]}
        data = await self._api("getUpdates", **params)
        return data.get("result", [])

    async def _handle_update(self, update: dict) -> None:
        message = update.get("message") or update.get("edited_message")
        if not message:
            return
        text = message.get("text", "").strip()
        if not text:
            return
        chat_id = str(message["chat"]["id"])

        # Allow users to switch persona via /persona <id>
        if text.startswith("/persona "):
            persona_id = text.split(maxsplit=1)[1].strip()
            await self._push_inbound(chat_id=chat_id, text="", persona_id=persona_id, is_system=True)
            await self.send_message(chat_id, f"Switched to persona: {persona_id}")
            return

        await self._push_inbound(chat_id=chat_id, text=text)

    # ------------------------------------------------------------------
    # HTTP helper
    # ------------------------------------------------------------------

    async def _api(self, method: str, **params) -> dict:
        url = f"{self._base}/{method}"
        assert self._session is not None
        async with self._session.post(url, json=params) as resp:
            resp.raise_for_status()
            return await resp.json()
