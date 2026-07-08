"""Presence tracking and direct (human-to-human) messaging.

Real-time-ish behaviour is achieved with simple REST polling on the client,
so there is no WebSocket dependency here.  A single module-level service
instance is reused across requests to avoid opening a new Mongo connection
on every poll.
"""

from datetime import datetime, timedelta, timezone

from bson import ObjectId
from pymongo import ASCENDING, MongoClient

from philoagents.config import settings
from philoagents.domain.message import DirectMessage

ONLINE_WINDOW_SECONDS = 30


def _conversation_key(user_a: str, user_b: str) -> str:
    return ":".join(sorted([user_a, user_b]))


class MessagingService:
    def __init__(self) -> None:
        self.client = MongoClient(settings.MONGO_URI, appname="philoagents")
        db = self.client[settings.MONGO_DB_NAME]
        self.users = db[settings.MONGO_USERS_COLLECTION]
        self.messages = db[settings.MONGO_MESSAGES_COLLECTION]

    def ensure_indexes(self) -> None:
        self.messages.create_index(
            [("conversation_key", ASCENDING), ("created_at", ASCENDING)]
        )
        self.messages.create_index([("to_user_id", ASCENDING), ("read", ASCENDING)])

    # --- Presence ------------------------------------------------------------

    def ping(self, user_id: str) -> None:
        try:
            self.users.update_one(
                {"_id": ObjectId(user_id)},
                {"$set": {"last_seen": datetime.now(timezone.utc)}},
            )
        except Exception:
            pass

    def online_users(self, exclude_user_id: str) -> list[dict]:
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=ONLINE_WINDOW_SECONDS)
        docs = self.users.find({"last_seen": {"$gte": cutoff}})
        result = []
        for d in docs:
            uid = str(d["_id"])
            if uid == exclude_user_id:
                continue
            result.append({"id": uid, "name": d.get("name", "")})
        return result

    def directory(self, exclude_user_id: str) -> list[dict]:
        """Everyone in the workspace, with an ``online`` flag.

        Lets a user message anyone — offline people simply read it later.
        """
        online_ids = {u["id"] for u in self.online_users(exclude_user_id)}
        result = []
        for d in self.users.find({}, {"name": 1}):
            uid = str(d["_id"])
            if uid == exclude_user_id:
                continue
            result.append(
                {"id": uid, "name": d.get("name", ""), "online": uid in online_ids}
            )
        result.sort(key=lambda u: (not u["online"], u["name"].lower()))
        return result

    # --- Direct messages -----------------------------------------------------

    def send(
        self, from_user_id: str, from_name: str, to_user_id: str, text: str
    ) -> DirectMessage:
        msg = DirectMessage(
            conversation_key=_conversation_key(from_user_id, to_user_id),
            from_user_id=from_user_id,
            from_name=from_name,
            to_user_id=to_user_id,
            text=text.strip(),
        )
        doc = msg.model_dump(exclude={"id"})
        self.messages.insert_one(doc)
        return msg

    def conversation(
        self, user_id: str, other_user_id: str, limit: int = 200
    ) -> list[dict]:
        key = _conversation_key(user_id, other_user_id)
        docs = list(
            self.messages.find({"conversation_key": key})
            .sort("created_at", ASCENDING)
            .limit(limit)
        )
        # Mark messages addressed to me as read.
        self.messages.update_many(
            {"conversation_key": key, "to_user_id": user_id, "read": False},
            {"$set": {"read": True}},
        )
        return [
            {
                "id": str(d["_id"]),
                "from_user_id": d["from_user_id"],
                "from_name": d.get("from_name", ""),
                "text": d["text"],
                "created_at": d["created_at"].isoformat(),
                "mine": d["from_user_id"] == user_id,
            }
            for d in docs
        ]

    def build_chat_context_for_user(self, user_id: str, limit: int = 60) -> str:
        """Format a user's recent direct messages for the AI agent's context.

        Only this user's own conversations are included, preserving privacy:
        the agent that serves a user can see that user's chats and nobody
        else's.
        """
        docs = list(
            self.messages.find(
                {"$or": [{"from_user_id": user_id}, {"to_user_id": user_id}]}
            )
            .sort("created_at", -1)
            .limit(limit)
        )
        if not docs:
            return ""
        docs.reverse()  # chronological order

        # Resolve the names of the other participants.
        other_ids = set()
        for d in docs:
            other = (
                d["to_user_id"] if d["from_user_id"] == user_id else d["from_user_id"]
            )
            other_ids.add(other)
        names: dict[str, str] = {}
        for oid in other_ids:
            try:
                u = self.users.find_one({"_id": ObjectId(oid)}, {"name": 1})
                names[oid] = (u or {}).get("name", "Someone")
            except Exception:
                names[oid] = "Someone"

        lines = []
        for d in docs:
            if d["from_user_id"] == user_id:
                partner = names.get(d["to_user_id"], "Someone")
                lines.append(f"You → {partner}: {d['text']}")
            else:
                partner = names.get(d["from_user_id"], "Someone")
                lines.append(f"{partner} → You: {d['text']}")
        return "\n".join(lines)

    def seed_demo_conversations(self) -> None:
        """Seed a believable DM history between the demo users (demo mode).

        Runs only when the messages collection is empty. The storyline is kept
        consistent with the demo Jira fixtures (see workflow/tools.py): the
        auth redesign slipped, the v2.0 release moved, and Arjun is blocked on
        an RFC approval — so agents can answer questions about these chats.
        """
        if self.messages.estimated_document_count() > 0:
            return

        users = {
            u.get("email", ""): {"id": str(u["_id"]), "name": u.get("name", "")}
            for u in self.users.find({"auth_provider": "demo"})
        }

        script = [
            ("priya@workverse.app", "rahul@workverse.app",
             "Heads up — Meera's auth redesign slipped by two days, so I'm moving the "
             "v2.0 release from Aug 10 to Aug 14. Updating the roadmap today (WV-99)."),
            ("rahul@workverse.app", "priya@workverse.app",
             "Fine by me — better than compressing QA. Announce the new date in #eng "
             "and flag it to support."),
            ("meera@workverse.app", "rahul@workverse.app",
             "The new auth screens (login + signup) are up in Figma for review. Final "
             "polish lands by Friday. Can you approve the auth RFC so Arjun can start "
             "the token work?"),
            ("rahul@workverse.app", "meera@workverse.app",
             "Nice work. I'll review the RFC today — expect approval by EOD."),
            ("arjun@workverse.app", "rahul@workverse.app",
             "OAuth token refresh (WV-112) is about halfway done, but I'm blocked on "
             "the RFC approval for the session-timeout decision."),
            ("rahul@workverse.app", "arjun@workverse.app",
             "On it — reviewing this afternoon. Assume 30-minute idle timeout for now."),
            ("priya@workverse.app", "arjun@workverse.app",
             "Can WV-108 (the mobile WebSocket reconnect bug) still make this sprint?"),
            ("arjun@workverse.app", "priya@workverse.app",
             "Yes, as long as the design review doesn't eat my Thursday. It's next "
             "after the token refresh work."),
            ("meera@workverse.app", "priya@workverse.app",
             "Dark mode tokens (WV-106) — okay to push those to v2.1? Auth screens "
             "are the priority this week."),
            ("priya@workverse.app", "meera@workverse.app",
             "Yes, v2.1 is fine. Auth first."),
            ("simran@workverse.app", "rahul@workverse.app",
             "Q3 offsite: does Sept 18–19 in Goa work? I need headcount confirmed by "
             "next week to lock the venue."),
        ]

        now = datetime.now(timezone.utc)
        docs = []
        for i, (from_email, to_email, text) in enumerate(script):
            sender, recipient = users.get(from_email), users.get(to_email)
            if not sender or not recipient:
                continue
            docs.append(
                {
                    "conversation_key": _conversation_key(sender["id"], recipient["id"]),
                    "from_user_id": sender["id"],
                    "from_name": sender["name"],
                    "to_user_id": recipient["id"],
                    "text": text,
                    "read": True,
                    "created_at": now - timedelta(minutes=(len(script) - i) * 47),
                }
            )

        # Leave the newest message of each conversation unread → demo unread badges.
        last_by_key: dict[str, dict] = {}
        for d in docs:
            last_by_key[d["conversation_key"]] = d
        for d in last_by_key.values():
            d["read"] = False

        if docs:
            self.messages.insert_many(docs)

    def unread_summary(self, user_id: str) -> list[dict]:
        pipeline = [
            {"$match": {"to_user_id": user_id, "read": False}},
            {
                "$group": {
                    "_id": "$from_user_id",
                    "from_name": {"$first": "$from_name"},
                    "count": {"$sum": 1},
                }
            },
        ]
        return [
            {
                "from_user_id": r["_id"],
                "from_name": r.get("from_name", ""),
                "count": r["count"],
            }
            for r in self.messages.aggregate(pipeline)
        ]


_service: MessagingService | None = None


def get_messaging_service() -> MessagingService:
    """Return the shared MessagingService (created on first use)."""
    global _service
    if _service is None:
        _service = MessagingService()
    return _service
