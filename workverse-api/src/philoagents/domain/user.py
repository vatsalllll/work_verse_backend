"""User domain model for WorkVerse authentication."""

from datetime import datetime, timezone

from pydantic import BaseModel, EmailStr, Field


class User(BaseModel):
    """A WorkVerse user account.

    A user may authenticate locally (email + password) or via an OAuth
    provider (Google / Slack).  For OAuth-only accounts ``hashed_password``
    is ``None``.
    """

    id: str | None = None
    name: str
    email: EmailStr
    hashed_password: str | None = None
    auth_provider: str = "local"  # "local" | "google" | "slack"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def public_dict(self) -> dict:
        """Safe representation to return to the client (no password hash)."""
        return {
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "auth_provider": self.auth_provider,
        }
