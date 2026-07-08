"""User persistence and authentication logic for WorkVerse."""

from bson import ObjectId
from loguru import logger
from pymongo import ASCENDING, MongoClient

from philoagents.config import settings
from philoagents.domain.user import User
from philoagents.infrastructure.security import hash_password, verify_password


class AuthError(Exception):
    """Raised on registration/login problems (duplicate email, bad credentials)."""


# Ready-made workspace members for demos (mirrors the 5 AI personas/roles).
DEMO_USERS = [
    {"name": "Rahul (CTO)", "email": "rahul@workverse.app"},
    {"name": "Arjun (Engineer)", "email": "arjun@workverse.app"},
    {"name": "Priya (PM)", "email": "priya@workverse.app"},
    {"name": "Meera (Designer)", "email": "meera@workverse.app"},
    {"name": "Simran (HR)", "email": "simran@workverse.app"},
]
DEMO_PASSWORD = "workverse"


class UserRepository:
    """Thin MongoDB data-access layer for the ``users`` collection."""

    def __init__(self) -> None:
        self.client = MongoClient(settings.MONGO_URI, appname="philoagents")
        self.collection = self.client[settings.MONGO_DB_NAME][
            settings.MONGO_USERS_COLLECTION
        ]

    def ensure_indexes(self) -> None:
        self.collection.create_index([("email", ASCENDING)], unique=True)
        logger.info("Ensured unique index on users.email")

    @staticmethod
    def _to_user(doc: dict | None) -> User | None:
        if not doc:
            return None
        doc = dict(doc)
        doc["id"] = str(doc.pop("_id"))
        return User(**doc)

    def get_by_email(self, email: str) -> User | None:
        return self._to_user(self.collection.find_one({"email": email.lower()}))

    def get_by_id(self, user_id: str) -> User | None:
        try:
            oid = ObjectId(user_id)
        except Exception:
            return None
        return self._to_user(self.collection.find_one({"_id": oid}))

    def create(self, user: User) -> User:
        doc = user.model_dump(exclude={"id"})
        doc["email"] = doc["email"].lower()
        result = self.collection.insert_one(doc)
        user.id = str(result.inserted_id)
        return user


class AuthService:
    """Registration and login for local (email + password) and OAuth users."""

    def __init__(self, repo: UserRepository | None = None) -> None:
        self.repo = repo or UserRepository()

    def register(self, name: str, email: str, password: str) -> User:
        if self.repo.get_by_email(email):
            raise AuthError("An account with this email already exists.")
        user = User(
            name=name.strip(),
            email=email.lower(),
            hashed_password=hash_password(password),
            auth_provider="local",
        )
        return self.repo.create(user)

    def login(self, email: str, password: str) -> User:
        user = self.repo.get_by_email(email)
        if not user or not verify_password(password, user.hashed_password):
            raise AuthError("Invalid email or password.")
        return user

    def seed_demo_users(self) -> None:
        """Create the demo workspace accounts if they don't already exist."""
        for entry in DEMO_USERS:
            if self.repo.get_by_email(entry["email"]):
                continue
            self.repo.create(
                User(
                    name=entry["name"],
                    email=entry["email"],
                    hashed_password=hash_password(DEMO_PASSWORD),
                    auth_provider="demo",
                )
            )

    def list_demo_users(self) -> list[dict]:
        """Public list of demo accounts (id + name) for the quick-login picker."""
        result = []
        for entry in DEMO_USERS:
            user = self.repo.get_by_email(entry["email"])
            if user:
                result.append({"id": user.id, "name": user.name, "email": user.email})
        return result

    def demo_login(self, email: str) -> User:
        """One-click login for a known demo account (no password required)."""
        if email.lower() not in {u["email"] for u in DEMO_USERS}:
            raise AuthError("Not a demo account.")
        user = self.repo.get_by_email(email)
        if not user:
            raise AuthError("Demo account not found.")
        return user

    def get_or_create_oauth_user(
        self, name: str, email: str, provider: str
    ) -> User:
        """Used by Google/Slack login (Phase B/C): find by email or create."""
        existing = self.repo.get_by_email(email)
        if existing:
            return existing
        user = User(
            name=name.strip() or email.split("@")[0],
            email=email.lower(),
            hashed_password=None,
            auth_provider=provider,
        )
        return self.repo.create(user)
