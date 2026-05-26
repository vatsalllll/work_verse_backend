from dataclasses import dataclass, field


@dataclass
class InboundMessage:
    """Strongly-typed envelope for all incoming messages.

    Produced by channel adapters (Telegram, Discord, Slack, etc.) and consumed
    by the AgentLoop.  Using a dataclass instead of a raw dict eliminates
    runtime KeyError bugs caused by typos.

    Attributes:
        session_key: Unique identifier combining channel + user/chat id.
                     Format: "<channel>:<id>"  e.g. "telegram:828124856"
        text:        The raw user input.
        persona_id:  Which persona (agent character) should respond.
        is_system:   True when the message is triggered autonomously (e.g. by
                     a cron job) rather than by a real user interaction.
    """

    session_key: str
    text: str
    persona_id: str = "default"
    is_system: bool = False


@dataclass
class OutboundMessage:
    """Strongly-typed envelope for all outgoing messages.

    Produced by the AgentLoop and consumed by channel adapters that match the
    session_key prefix.

    Attributes:
        session_key:      Same format as InboundMessage.session_key so adapters
                          can route the reply back to the correct chat.
        text:             The response text to deliver to the user.
        is_tool_progress: When True the adapter should render this as an
                          italicised status hint (e.g. "_searching knowledge
                          base…_") rather than a final answer.
    """

    session_key: str
    text: str
    is_tool_progress: bool = False
