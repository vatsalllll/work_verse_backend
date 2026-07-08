"""Direct (human-to-human) message model for WorkVerse peer chat."""

from datetime import datetime, timezone

from pydantic import BaseModel, Field


class DirectMessage(BaseModel):
    """A single text message from one user to another.

    ``conversation_key`` is the two user ids sorted and joined, so both
    directions of a conversation share the same key.
    """

    id: str | None = None
    conversation_key: str
    from_user_id: str
    from_name: str
    to_user_id: str
    text: str
    read: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
