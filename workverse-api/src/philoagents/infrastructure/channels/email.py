"""Email channel adapter — IMAP (receive) + SMTP (send).

Uses only Python stdlib (``imaplib``, ``smtplib``, ``email``) so no extra
dependencies are required.

Convention:
  - The email Subject line is the user's prompt.
  - Replies are sent back to the sender's address.

Session key format: ``email:<sender_address>``
  e.g. ``email:alice@example.com``

Setup — populate in .env:
  EMAIL_IMAP_HOST, EMAIL_IMAP_PORT, EMAIL_SMTP_HOST, EMAIL_SMTP_PORT,
  EMAIL_ADDRESS, EMAIL_PASSWORD
"""

import asyncio
import email as email_lib
import imaplib
import smtplib
from email.mime.text import MIMEText

from loguru import logger

from philoagents.infrastructure.messaging import MessageBus

from .base import BaseChannel

_POLL_INTERVAL = 30  # seconds between IMAP checks


class EmailChannel(BaseChannel):
    prefix = "email"

    def __init__(
        self,
        imap_host: str,
        imap_port: int,
        smtp_host: str,
        smtp_port: int,
        address: str,
        password: str,
        bus: MessageBus,
        default_persona_id: str = "default",
    ) -> None:
        super().__init__(bus=bus, default_persona_id=default_persona_id)
        self._imap_host = imap_host
        self._imap_port = imap_port
        self._smtp_host = smtp_host
        self._smtp_port = smtp_port
        self._address = address
        self._password = password
        self._running = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        self._running = True
        logger.info(f"EmailChannel started — polling {self._address} every {_POLL_INTERVAL}s")
        await self._poll_loop()

    async def stop(self) -> None:
        self._running = False
        logger.info("EmailChannel stopped")

    # ------------------------------------------------------------------
    # Sending
    # ------------------------------------------------------------------

    async def send_message(self, chat_id: str, text: str) -> None:
        """Send email reply to *chat_id* (the sender's email address)."""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._send_sync, chat_id, text)

    # ------------------------------------------------------------------
    # Internal polling
    # ------------------------------------------------------------------

    async def _poll_loop(self) -> None:
        while self._running:
            try:
                loop = asyncio.get_event_loop()
                messages = await loop.run_in_executor(None, self._fetch_unseen)
                for sender, subject in messages:
                    await self._push_inbound(chat_id=sender, text=subject)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning(f"EmailChannel poll error: {exc}")
            await asyncio.sleep(_POLL_INTERVAL)

    def _fetch_unseen(self) -> list[tuple[str, str]]:
        """Fetch unseen emails and return (sender, subject) pairs."""
        results: list[tuple[str, str]] = []
        try:
            mail = imaplib.IMAP4_SSL(self._imap_host, self._imap_port)
            mail.login(self._address, self._password)
            mail.select("INBOX")
            _, data = mail.search(None, "UNSEEN")
            ids = data[0].split()
            for uid in ids:
                _, msg_data = mail.fetch(uid, "(RFC822)")
                raw = msg_data[0][1]
                msg = email_lib.message_from_bytes(raw)
                sender = email_lib.utils.parseaddr(msg["From"])[1]
                subject = msg.get("Subject", "").strip()
                if sender and subject:
                    results.append((sender, subject))
                # Mark as seen
                mail.store(uid, "+FLAGS", "\\Seen")
            mail.logout()
        except Exception as exc:
            logger.warning(f"IMAP fetch error: {exc}")
        return results

    def _send_sync(self, to_address: str, text: str) -> None:
        msg = MIMEText(text, "plain")
        msg["Subject"] = "Reply from WorkVerse"
        msg["From"] = self._address
        msg["To"] = to_address
        try:
            with smtplib.SMTP_SSL(self._smtp_host, self._smtp_port) as server:
                server.login(self._address, self._password)
                server.sendmail(self._address, [to_address], msg.as_string())
        except Exception as exc:
            logger.warning(f"SMTP send error: {exc}")
