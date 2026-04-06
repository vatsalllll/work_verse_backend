import asyncio

from .events import InboundMessage, OutboundMessage


class MessageBus:
    """Central async event bus — the nervous system of the multi-channel architecture.

    Uses a double-buffer design:
    - ``inbound``  — channel adapters push user messages here; the AgentLoop
                     drains it.
    - ``outbound`` — the AgentLoop pushes responses here; the ChannelManager
                     dispatcher routes them back to the right channel adapter.

    Both queues are unbounded so spikes in traffic are absorbed into RAM
    rather than dropped (back-pressure is handled by the LLM provider's own
    rate limits).
    """

    def __init__(self) -> None:
        self.inbound: asyncio.Queue[InboundMessage] = asyncio.Queue()
        self.outbound: asyncio.Queue[OutboundMessage] = asyncio.Queue()

    # ------------------------------------------------------------------
    # Inbound helpers
    # ------------------------------------------------------------------

    async def send_inbound(self, msg: InboundMessage) -> None:
        """Non-blocking enqueue of an inbound message (< 0.1 ms)."""
        await self.inbound.put(msg)

    async def receive_inbound(self) -> InboundMessage:
        """Block until an inbound message is available, then return it."""
        return await self.inbound.get()

    # ------------------------------------------------------------------
    # Outbound helpers
    # ------------------------------------------------------------------

    async def send_outbound(self, msg: OutboundMessage) -> None:
        """Non-blocking enqueue of an outbound message."""
        await self.outbound.put(msg)

    async def receive_outbound(self) -> OutboundMessage:
        """Block until an outbound message is available, then return it."""
        return await self.outbound.get()
