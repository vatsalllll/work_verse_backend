from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", extra="ignore", env_file_encoding="utf-8"
    )

    # --- GROQ Configuration ---
    GROQ_API_KEY: str
    GROQ_LLM_MODEL: str = "llama-3.3-70b-versatile"
    GROQ_LLM_MODEL_CONTEXT_SUMMARY: str = "llama-3.1-8b-instant"
    
    # --- OpenAI Configuration (Optional: for evaluation) ---
    OPENAI_API_KEY: str | None = Field(
        default=None, description="API key for OpenAI services (evaluation only)."
    )

    # --- MongoDB Configuration ---
    MONGO_URI: str = Field(
        default="mongodb://philoagents:philoagents@local_dev_atlas:27017/?directConnection=true",
        description="Connection URI for the local MongoDB Atlas instance.",
    )
    MONGO_DB_NAME: str = "philoagents"
    MONGO_STATE_CHECKPOINT_COLLECTION: str = "philosopher_state_checkpoints"
    MONGO_STATE_WRITES_COLLECTION: str = "philosopher_state_writes"
    MONGO_LONG_TERM_MEMORY_COLLECTION: str = "philosopher_long_term_memory"
    MONGO_USERS_COLLECTION: str = "users"
    MONGO_MESSAGES_COLLECTION: str = "direct_messages"

    # --- Authentication (JWT) ---
    JWT_SECRET: str = Field(
        default="dev-only-insecure-secret-change-me",
        description="Secret used to sign auth tokens. MUST be overridden in production.",
    )
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRY_MINUTES: int = 60 * 24 * 7  # 7 days

    # --- Demo mode ---
    # When True, the API seeds a set of ready-made workspace accounts and allows
    # one-click "log in as <person>" for easy demos.  Turn OFF in production.
    DEMO_MODE: bool = True

    # --- OAuth (Google / Slack) — Phase B/C, optional ---
    FRONTEND_URL: str = Field(
        default="http://localhost:8080",
        description="Where to redirect the browser back to after an OAuth login.",
    )
    OAUTH_REDIRECT_BASE: str = Field(
        default="http://localhost:8000",
        description="Public base URL of this API, used to build OAuth callback URLs.",
    )
    GOOGLE_CLIENT_ID: str | None = Field(default=None)
    GOOGLE_CLIENT_SECRET: str | None = Field(default=None)
    SLACK_CLIENT_ID: str | None = Field(default=None)
    SLACK_CLIENT_SECRET: str | None = Field(default=None)

    # --- Jira Configuration (optional) ---
    # Set all three to enable the `jira_my_tasks` tool. When any is missing the
    # tool is not registered and personas fall back to plain conversation.
    JIRA_BASE_URL: str | None = Field(
        default=None,
        description='Base URL of your Jira Cloud site, e.g. "https://your-company.atlassian.net".',
    )
    JIRA_EMAIL: str | None = Field(
        default=None,
        description="Email of the Jira account whose API token is used (Basic auth user).",
    )
    JIRA_API_TOKEN: str | None = Field(
        default=None,
        description="Jira API token (created at id.atlassian.com → Security → API tokens).",
    )

    @property
    def JIRA_ENABLED(self) -> bool:
        """True only when every Jira credential is present."""
        return bool(self.JIRA_BASE_URL and self.JIRA_EMAIL and self.JIRA_API_TOKEN)

    # --- Comet ML & Opik Configuration ---
    COMET_API_KEY: str | None = Field(
        default=None, description="API key for Comet ML and Opik services."
    )
    COMET_PROJECT: str = Field(
        default="philoagents_course",
        description="Project name for Comet ML and Opik tracking.",
    )

    # --- Agents Configuration ---
    TOTAL_MESSAGES_SUMMARY_TRIGGER: int = 30
    TOTAL_MESSAGES_AFTER_SUMMARY: int = 5

    # --- RAG Configuration ---
    RAG_TEXT_EMBEDDING_MODEL_ID: str = "sentence-transformers/all-MiniLM-L6-v2"
    RAG_TEXT_EMBEDDING_MODEL_DIM: int = 384
    RAG_TOP_K: int = 3
    RAG_DEVICE: str = "cpu"
    RAG_CHUNK_SIZE: int = 256

    # --- Paths Configuration ---
    EVALUATION_DATASET_FILE_PATH: Path = Path("data/evaluation_dataset.json")
    EXTRACTION_METADATA_FILE_PATH: Path = Path("data/extraction_metadata.json")

    # --- Persona Configuration ---
    DEFAULT_PERSONA_ID: str = Field(
        default="swe",
        description="Default persona used by channel adapters when no explicit persona is set.",
    )

    # =========================================================================
    # Channel Configuration
    # All channel fields are optional — leave unset to disable that channel.
    # The ChannelManager only imports a channel adapter when its token/key is
    # present, so unused channels have zero RAM footprint.
    # =========================================================================

    # --- Telegram ---
    TELEGRAM_BOT_TOKEN: str | None = Field(
        default=None,
        description="Bot token from @BotFather.  Set to enable the Telegram channel.",
    )

    # --- Discord ---
    DISCORD_BOT_TOKEN: str | None = Field(
        default=None,
        description="Bot token from the Discord Developer Portal.  Set to enable Discord.",
    )

    # --- Slack (Socket Mode) ---
    SLACK_BOT_TOKEN: str | None = Field(
        default=None,
        description="Bot OAuth token (xoxb-…).  Set alongside SLACK_APP_TOKEN to enable Slack.",
    )
    SLACK_APP_TOKEN: str | None = Field(
        default=None,
        description="App-level token (xapp-…) for Socket Mode.  Required together with SLACK_BOT_TOKEN.",
    )

    # --- WhatsApp (Twilio) ---
    TWILIO_ACCOUNT_SID: str | None = Field(
        default=None,
        description="Twilio account SID.  Required to enable the WhatsApp channel.",
    )
    TWILIO_AUTH_TOKEN: str | None = Field(
        default=None,
        description="Twilio auth token.",
    )
    TWILIO_WHATSAPP_FROM: str | None = Field(
        default=None,
        description='Twilio WhatsApp sender number, e.g. "whatsapp:+14155238886".',
    )

    # --- Email (IMAP / SMTP) ---
    EMAIL_ADDRESS: str | None = Field(
        default=None,
        description="Email address to receive and send messages from.  Set to enable the Email channel.",
    )
    EMAIL_PASSWORD: str | None = Field(
        default=None,
        description="Email account password (or app-specific password).",
    )
    EMAIL_IMAP_HOST: str = "imap.gmail.com"
    EMAIL_IMAP_PORT: int = 993
    EMAIL_SMTP_HOST: str = "smtp.gmail.com"
    EMAIL_SMTP_PORT: int = 465


settings = Settings()
