"""Discord channel adapter — persistent WebSocket via discord.py.

Requires: ``pip install discord.py``

Session key format: ``discord:<channel_id>``
"""

import asyncio

from loguru import logger

from philoagents.infrastructure.messaging import MessageBus

from .base import BaseChannel

try:
    import discord

    _DISCORD_AVAILABLE = True
except ImportError:  # pragma: no cover
    _DISCORD_AVAILABLE = False


class DiscordChannel(BaseChannel):
    prefix = "discord"

    def __init__(
        self,
        token: str,
        bus: MessageBus,
        default_persona_id: str = "default",
        command_prefix: str = "!",
    ) -> None:
        super().__init__(bus=bus, default_persona_id=default_persona_id)
        if not _DISCORD_AVAILABLE:
            raise ImportError("discord.py is required: pip install discord.py")

        self._token = token
        self._command_prefix = command_prefix
        self._client: "discord.Client | None" = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        self._client = discord.Client(intents=intents)

        @self._client.event
        async def on_ready():
            logger.info(f"DiscordChannel logged in as {self._client.user}")

        @self._client.event
        async def on_message(message: "discord.Message"):
            if message.author == self._client.user:
                return  # ignore own messages

            text = message.content.strip()
            # Strip @mentions that would confuse the LLM
            for mention in message.mentions:
                text = text.replace(f"<@{mention.id}>", "").replace(f"<@!{mention.id}>", "")
            text = text.strip()

            if not text:
                return

            chat_id = str(message.channel.id)

            if text.startswith(f"{self._command_prefix}persona "):
                persona_id = text.split(maxsplit=1)[1].strip()
                await self._push_inbound(chat_id=chat_id, text="", persona_id=persona_id, is_system=True)
                await message.channel.send(f"Switched to persona: **{persona_id}**")
                return

            await self._push_inbound(chat_id=chat_id, text=text)

        logger.info("DiscordChannel starting WebSocket connection")
        # discord.py's start() runs its own event loop internally
        asyncio.create_task(self._client.start(self._token))

    async def stop(self) -> None:
        if self._client:
            await self._client.close()
        logger.info("DiscordChannel stopped")

    # ------------------------------------------------------------------
    # Sending
    # ------------------------------------------------------------------

    async def send_message(self, chat_id: str, text: str) -> None:
        if not self._client:
            return
        channel = self._client.get_channel(int(chat_id))
        if channel is None:
            channel = await self._client.fetch_channel(int(chat_id))
        # Discord limit is 2000 chars
        chunks = [text[i : i + 2000] for i in range(0, len(text), 2000)]
        for chunk in chunks:
            await channel.send(chunk)
