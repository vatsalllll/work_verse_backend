"""WhatsApp channel adapter — Twilio WhatsApp API.

Inbound messages arrive as POST webhooks from Twilio.  This adapter registers
a FastAPI route on the shared app so no separate web server is needed.

Outbound messages are delivered via the Twilio REST API.

Requires: ``pip install twilio``

Session key format: ``whatsapp:<sender_number>``
  e.g. ``whatsapp:+919876543210``

Setup:
1. Create a Twilio account and enable the WhatsApp Sandbox (or buy a number).
2. Set the webhook URL in Twilio console to:
   ``https://<your-domain>/webhook/whatsapp``
3. Populate TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_WHATSAPP_FROM
   in your .env file.
"""

from loguru import logger

from philoagents.infrastructure.messaging import MessageBus

from .base import BaseChannel

try:
    from twilio.rest import Client as TwilioClient

    _TWILIO_AVAILABLE = True
except ImportError:  # pragma: no cover
    _TWILIO_AVAILABLE = False


class WhatsAppChannel(BaseChannel):
    prefix = "whatsapp"

    def __init__(
        self,
        account_sid: str,
        auth_token: str,
        from_number: str,  # e.g. "whatsapp:+14155238886"
        bus: MessageBus,
        default_persona_id: str = "default",
        fastapi_app=None,  # Pass the FastAPI app to register the webhook route
    ) -> None:
        super().__init__(bus=bus, default_persona_id=default_persona_id)
        if not _TWILIO_AVAILABLE:
            raise ImportError("twilio is required: pip install twilio")

        self._account_sid = account_sid
        self._auth_token = auth_token
        self._from_number = from_number
        self._client: TwilioClient | None = None
        self._fastapi_app = fastapi_app

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        self._client = TwilioClient(self._account_sid, self._auth_token)

        if self._fastapi_app is not None:
            self._register_webhook(self._fastapi_app)

        logger.info("WhatsAppChannel started — webhook route registered at /webhook/whatsapp")

    async def stop(self) -> None:
        logger.info("WhatsAppChannel stopped")

    # ------------------------------------------------------------------
    # Sending
    # ------------------------------------------------------------------

    async def send_message(self, chat_id: str, text: str) -> None:
        """Deliver text to a WhatsApp number via Twilio REST API.

        Args:
            chat_id: The recipient's WhatsApp number, e.g. "+919876543210".
                     The "whatsapp:" prefix is added automatically.
        """
        if self._client is None:
            return
        to = chat_id if chat_id.startswith("whatsapp:") else f"whatsapp:{chat_id}"
        self._client.messages.create(body=text, from_=self._from_number, to=to)

    # ------------------------------------------------------------------
    # Webhook route (registered on FastAPI app)
    # ------------------------------------------------------------------

    def _register_webhook(self, app) -> None:
        from fastapi import Request
        from fastapi.responses import PlainTextResponse

        @app.post("/webhook/whatsapp")
        async def whatsapp_webhook(request: Request):
            form = await request.form()
            sender = str(form.get("From", "")).replace("whatsapp:", "")
            body = str(form.get("Body", "")).strip()

            if not body or not sender:
                return PlainTextResponse("")

            if body.lower().startswith("/persona "):
                persona_id = body.split(maxsplit=1)[1].strip()
                await self._push_inbound(
                    chat_id=sender, text="", persona_id=persona_id, is_system=True
                )
                await self.send_message(sender, f"Switched to persona: {persona_id}")
                return PlainTextResponse("")

            await self._push_inbound(chat_id=sender, text=body)
            return PlainTextResponse("")
