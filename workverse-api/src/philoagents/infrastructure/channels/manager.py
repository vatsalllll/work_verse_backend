"""ChannelManager — dynamic lazy-loader and outbound dispatcher.

Architecture:
  - Reads ``settings`` to decide which channels are enabled.
  - Imports channel adapters only when their config is present (zero RAM cost
    for unused channels).
  - Runs each adapter's ``start()`` as a background asyncio Task.
  - Runs a single ``_dispatch_outbound`` task that reads from ``bus.outbound``
    and routes each ``OutboundMessage`` to the correct channel based on the
    ``session_key`` prefix.
  - Runs the ``AgentLoop`` — reads from ``bus.inbound``, invokes the LangGraph
    workflow, pushes the reply to ``bus.outbound``.
"""

import asyncio
from typing import TYPE_CHECKING

from loguru import logger

from philoagents.config import settings
from philoagents.infrastructure.messaging import InboundMessage, MessageBus, OutboundMessage

from .base import BaseChannel

if TYPE_CHECKING:
    from fastapi import FastAPI


class AgentLoop:
    """Reads InboundMessages from the bus, calls the LangGraph workflow, and
    pushes OutboundMessages back onto the bus.

    This decouples the IO-bound channel sockets from the network-bound LLM
    execution, eliminating race conditions and enabling per-session state.
    """

    def __init__(self, bus: MessageBus) -> None:
        self.bus = bus

    async def run(self) -> None:
        from philoagents.application.conversation_service.generate_response import (
            get_persona_response,
        )
        from philoagents.domain.persona_factory import PersonaFactory

        factory = PersonaFactory()
        logger.info("AgentLoop started — waiting for inbound messages")

        while True:
            msg: InboundMessage = await self.bus.receive_inbound()

            # system messages used for persona switching — no LLM call needed
            if msg.is_system and not msg.text:
                continue

            asyncio.create_task(self._process(msg, factory, get_persona_response))

    async def _process(self, msg: InboundMessage, factory, get_persona_response) -> None:
        try:
            persona = factory.get_persona(msg.persona_id)

            # Emit a "thinking" progress hint immediately so the user knows
            # the bot is active during potentially long LLM calls.
            await self.bus.send_outbound(
                OutboundMessage(
                    session_key=msg.session_key,
                    text="_thinking…_",
                    is_tool_progress=True,
                )
            )

            response, _ = await get_persona_response(
                messages=msg.text,
                persona_id=msg.session_key,  # use session_key as thread_id for per-user history
                persona_name=persona.name,
                persona_perspective=persona.perspective,
                persona_style=persona.style,
                persona_context="",
            )

            await self.bus.send_outbound(
                OutboundMessage(session_key=msg.session_key, text=response)
            )
        except Exception as exc:
            logger.error(f"AgentLoop error for session {msg.session_key}: {exc}")
            await self.bus.send_outbound(
                OutboundMessage(
                    session_key=msg.session_key,
                    text="Sorry, I encountered an error. Please try again.",
                )
            )


class ChannelManager:
    """Orchestrates all active channels and the AgentLoop.

    Usage (inside FastAPI lifespan)::

        manager = ChannelManager(app=app)
        await manager.start()
        yield
        await manager.stop()
    """

    def __init__(self, app: "FastAPI | None" = None) -> None:
        self.bus = MessageBus()
        self._channels: dict[str, BaseChannel] = {}
        self._tasks: list[asyncio.Task] = []
        self._app = app
        self._load_channels()

    # ------------------------------------------------------------------
    # Channel loader (dynamic / lazy)
    # ------------------------------------------------------------------

    def _load_channels(self) -> None:
        """Import and instantiate only the channels whose config is present."""

        # --- Telegram ---
        if settings.TELEGRAM_BOT_TOKEN:
            from .telegram import TelegramChannel

            self._channels["telegram"] = TelegramChannel(
                token=settings.TELEGRAM_BOT_TOKEN,
                bus=self.bus,
                default_persona_id=settings.DEFAULT_PERSONA_ID,
            )
            logger.info("TelegramChannel registered")

        # --- Discord ---
        if settings.DISCORD_BOT_TOKEN:
            from .discord import DiscordChannel

            self._channels["discord"] = DiscordChannel(
                token=settings.DISCORD_BOT_TOKEN,
                bus=self.bus,
                default_persona_id=settings.DEFAULT_PERSONA_ID,
            )
            logger.info("DiscordChannel registered")

        # --- Slack ---
        if settings.SLACK_BOT_TOKEN and settings.SLACK_APP_TOKEN:
            from .slack import SlackChannel

            self._channels["slack"] = SlackChannel(
                bot_token=settings.SLACK_BOT_TOKEN,
                app_token=settings.SLACK_APP_TOKEN,
                bus=self.bus,
                default_persona_id=settings.DEFAULT_PERSONA_ID,
            )
            logger.info("SlackChannel registered")

        # --- WhatsApp (Twilio) ---
        if settings.TWILIO_ACCOUNT_SID and settings.TWILIO_AUTH_TOKEN and settings.TWILIO_WHATSAPP_FROM:
            from .whatsapp import WhatsAppChannel

            self._channels["whatsapp"] = WhatsAppChannel(
                account_sid=settings.TWILIO_ACCOUNT_SID,
                auth_token=settings.TWILIO_AUTH_TOKEN,
                from_number=settings.TWILIO_WHATSAPP_FROM,
                bus=self.bus,
                default_persona_id=settings.DEFAULT_PERSONA_ID,
                fastapi_app=self._app,
            )
            logger.info("WhatsAppChannel registered")

        # --- Email ---
        if settings.EMAIL_ADDRESS and settings.EMAIL_PASSWORD:
            from .email import EmailChannel

            self._channels["email"] = EmailChannel(
                imap_host=settings.EMAIL_IMAP_HOST,
                imap_port=settings.EMAIL_IMAP_PORT,
                smtp_host=settings.EMAIL_SMTP_HOST,
                smtp_port=settings.EMAIL_SMTP_PORT,
                address=settings.EMAIL_ADDRESS,
                password=settings.EMAIL_PASSWORD,
                bus=self.bus,
                default_persona_id=settings.DEFAULT_PERSONA_ID,
            )
            logger.info("EmailChannel registered")

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        # Start each channel adapter as a background task
        for name, channel in self._channels.items():
            task = asyncio.create_task(channel.start(), name=f"channel:{name}")
            self._tasks.append(task)

        # Start the outbound dispatcher
        self._tasks.append(
            asyncio.create_task(self._dispatch_outbound(), name="channel:dispatcher")
        )

        # Start the AgentLoop
        agent_loop = AgentLoop(bus=self.bus)
        self._tasks.append(
            asyncio.create_task(agent_loop.run(), name="agent:loop")
        )

        logger.info(
            f"ChannelManager started with {len(self._channels)} channel(s): "
            f"{list(self._channels.keys()) or 'none'}"
        )

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        for channel in self._channels.values():
            await channel.stop()
        logger.info("ChannelManager stopped")

    # ------------------------------------------------------------------
    # Outbound dispatcher
    # ------------------------------------------------------------------

    async def _dispatch_outbound(self) -> None:
        """Read OutboundMessages and route them to the correct channel adapter."""
        while True:
            msg: OutboundMessage = await self.bus.receive_outbound()
            prefix = msg.session_key.split(":")[0]
            chat_id = msg.session_key.split(":", 1)[1]

            channel = self._channels.get(prefix)
            if channel is None:
                logger.warning(f"No channel registered for prefix '{prefix}' — dropping message")
                continue

            try:
                # For tool-progress hints, render as italics if the platform
                # supports markdown (Telegram/Discord/Slack all do).
                text = f"_{msg.text}_" if msg.is_tool_progress else msg.text
                await channel.send_message(chat_id=chat_id, text=text)
            except Exception as exc:
                logger.error(f"Failed to dispatch to {msg.session_key}: {exc}")
