import abc

from philoagents.infrastructure.messaging import InboundMessage, MessageBus


class BaseChannel(abc.ABC):
    """Abstract base class that every channel adapter must implement.

    Enforces the Liskov Substitution Principle — the ChannelManager never
    speaks to a concrete adapter directly; it only calls methods defined here.

    Subclasses are responsible for:
    1. Connecting to their external platform (Telegram, Discord, …).
    2. Converting platform-specific payloads to ``InboundMessage`` objects and
       pushing them onto the bus.
    3. Sending ``OutboundMessage`` text back to the correct chat when asked.
    """

    def __init__(self, bus: MessageBus, default_persona_id: str = "default") -> None:
        self.bus = bus
        self.default_persona_id = default_persona_id

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    @abc.abstractmethod
    async def start(self) -> None:
        """Start listening for incoming messages (polling / WebSocket / IMAP…)."""

    @abc.abstractmethod
    async def stop(self) -> None:
        """Gracefully disconnect from the platform."""

    # ------------------------------------------------------------------
    # Sending
    # ------------------------------------------------------------------

    @abc.abstractmethod
    async def send_message(self, chat_id: str, text: str) -> None:
        """Deliver *text* to the platform chat identified by *chat_id*."""

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @property
    @abc.abstractmethod
    def prefix(self) -> str:
        """Channel prefix used in session_key routing (e.g. ``"telegram"``).

        The ChannelManager matches ``OutboundMessage.session_key`` against
        ``<prefix>:<chat_id>`` to decide which adapter should deliver the
        message.
        """

    async def _push_inbound(
        self,
        chat_id: str,
        text: str,
        persona_id: str | None = None,
        is_system: bool = False,
    ) -> None:
        """Convenience helper — build and enqueue an InboundMessage."""
        msg = InboundMessage(
            session_key=f"{self.prefix}:{chat_id}",
            text=text,
            persona_id=persona_id or self.default_persona_id,
            is_system=is_system,
        )
        await self.bus.send_inbound(msg)
