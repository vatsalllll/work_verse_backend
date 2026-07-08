"""Tool registry for the conversation workflow.

Tools are keyed by a capability *slug*. Each persona declares which slugs it may
use (see ``Persona.tools``); the chain binds only that subset, while the graph's
single ``ToolNode`` holds every registered tool and just executes whatever was
actually called.

Adding a new integration (GitHub, Slack, Notion, …) is a two-step change:
register a tool here, then list its slug on the relevant personas.
"""

from functools import lru_cache

from langchain.tools.retriever import create_retriever_tool
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool, tool
from loguru import logger

from philoagents.application.rag.retrievers import get_retriever
from philoagents.config import settings
from philoagents.infrastructure.jira_client import JiraClient, JiraError


@lru_cache(maxsize=1)
def _get_retriever():
    """Lazy-load the retriever (and embedding model) on first use."""
    return get_retriever(
        embedding_model_id=settings.RAG_TEXT_EMBEDDING_MODEL_ID,
        k=settings.RAG_TOP_K,
        device=settings.RAG_DEVICE,
    )


@lru_cache(maxsize=1)
def _get_retriever_tool() -> BaseTool:
    """Lazy-load the retriever tool on first use."""
    return create_retriever_tool(
        _get_retriever(),
        "retrieve_philosopher_context",
        "Search and return information about a specific philosopher. Always use this tool when the user asks you about a philosopher, their works, ideas or historical context.",
    )


def _format_issues(issues: list[dict]) -> str:
    """Render trimmed Jira issues into a compact, model-friendly block."""
    lines = []
    for i in issues:
        bits = [f"{i['key']}: {i['summary']}"]
        if i.get("status"):
            bits.append(f"status={i['status']}")
        if i.get("priority"):
            bits.append(f"priority={i['priority']}")
        if i.get("duedate"):
            bits.append(f"due={i['duedate']}")
        lines.append(" | ".join(bits))
    return "\n".join(lines)


# Realistic demo tickets per demo-workspace user (used when DEMO_MODE is on and
# no real Jira is connected). Keyed by user email; keep in sync with the demo
# users seeded by AuthService and the seeded demo DM conversations.
_DEMO_ISSUES: dict[str, list[dict]] = {
    "rahul@workverse.app": [
        {"key": "WV-98", "summary": "Approve auth architecture RFC", "status": "To Do", "priority": "High"},
        {"key": "WV-101", "summary": "Review Q3 infra budget proposal", "status": "In Progress", "priority": "High"},
        {"key": "WV-87", "summary": "Vendor evaluation: observability platform", "status": "To Do", "priority": "Medium"},
    ],
    "arjun@workverse.app": [
        {"key": "WV-112", "summary": "Implement OAuth token refresh flow", "status": "In Progress", "priority": "High", "duedate": "2026-07-10"},
        {"key": "WV-108", "summary": "Fix WebSocket reconnect bug on mobile", "status": "To Do", "priority": "High"},
        {"key": "WV-95", "summary": "Add rate limiting to /chat API", "status": "To Do", "priority": "Medium"},
        {"key": "WV-90", "summary": "Code review: payments service PR #214", "status": "Done"},
    ],
    "priya@workverse.app": [
        {"key": "WV-115", "summary": "Finalise v2.0 release plan", "status": "In Progress", "priority": "High", "duedate": "2026-07-09"},
        {"key": "WV-104", "summary": "User interviews for onboarding flow", "status": "To Do", "priority": "Medium"},
        {"key": "WV-99", "summary": "Update roadmap after auth redesign slip", "status": "To Do", "priority": "High"},
    ],
    "meera@workverse.app": [
        {"key": "WV-110", "summary": "Auth screens redesign (login + signup)", "status": "In Progress", "priority": "High", "duedate": "2026-07-10"},
        {"key": "WV-106", "summary": "Design system: dark mode tokens", "status": "To Do", "priority": "Medium"},
        {"key": "WV-92", "summary": "Onboarding illustrations v2", "status": "Done"},
    ],
    "simran@workverse.app": [
        {"key": "WV-113", "summary": "Plan Q3 engineering offsite", "status": "In Progress", "priority": "Medium"},
        {"key": "WV-103", "summary": "Close senior backend engineer role", "status": "To Do", "priority": "High"},
    ],
}


def _demo_issues_for(user_email: str, status: str | None) -> list[dict] | None:
    issues = _DEMO_ISSUES.get(user_email.lower())
    if issues is None:
        return None
    if status:
        issues = [i for i in issues if i.get("status", "").lower() == status.lower()]
    return issues


@tool
async def jira_my_tasks(
    config: RunnableConfig,
    status: str | None = None,
) -> str:
    """Fetch the current user's Jira issues (their assigned tasks/tickets).

    Use this whenever the user asks about their tasks, tickets, issues, sprint
    work, or what they should work on next. Optionally filter by a Jira status
    such as "To Do", "In Progress", or "Done". Returns the real issues assigned
    to the person you are talking to — never invent tickets.
    """
    if not settings.JIRA_ENABLED:
        if settings.DEMO_MODE:
            configurable = (config or {}).get("configurable", {})
            demo_email = configurable.get("user_email") or ""
            demo_issues = _demo_issues_for(demo_email, status)
            if demo_issues is not None:
                if not demo_issues:
                    scope = f' with status "{status}"' if status else ""
                    return f"No Jira issues are currently assigned to you{scope}."
                return f"Jira issues assigned to {demo_email}:\n{_format_issues(demo_issues)}"
        return "Jira isn't connected yet, so I can't look up real tasks right now."

    configurable = (config or {}).get("configurable", {})
    user_email = configurable.get("user_email")
    if not user_email:
        return "I couldn't determine who you are, so I can't look up your Jira tasks."

    try:
        async with JiraClient() as client:
            issues = await client.get_issues_for(user_email, status=status)
    except JiraError as e:
        logger.warning(f"jira_my_tasks failed: {e}")
        return "I couldn't reach Jira just now. Please try again in a moment."

    if not issues:
        scope = f' with status "{status}"' if status else ""
        return f"No Jira issues are currently assigned to you{scope}."

    return f"Jira issues assigned to {user_email}:\n{_format_issues(issues)}"


# --- Registry -------------------------------------------------------------


@lru_cache(maxsize=1)
def _registry() -> dict[str, BaseTool]:
    """Build the slug -> tool map.

    ``jira_my_tasks`` is only registered when Jira credentials are configured.
    Binding a tool the model cannot successfully use invites malformed
    text-form tool calls (Groq/Llama leaks ``<function=...>`` markup into the
    chat), so unconfigured integrations are left unbound entirely — the persona
    then answers from its own knowledge instead of attempting a dead call.

    The philosopher retriever (``_get_retriever_tool``) is intentionally NOT
    registered: it is a leftover from the upstream project, no persona uses it,
    and registering it would eagerly load the embedding model into the ToolNode.
    Re-add it here (and to a persona's ``tools``) to reintroduce it.
    """
    registry: dict[str, BaseTool] = {}
    if settings.JIRA_ENABLED or settings.DEMO_MODE:
        # In demo mode the tool serves realistic fixture data (_DEMO_ISSUES)
        # so the full tool-call flow can be demonstrated without a real Jira.
        registry["jira_my_tasks"] = jira_my_tasks
    else:
        logger.info("Jira credentials missing — jira_my_tasks tool not registered.")
    return registry


def get_tools_for(tool_slugs: list[str]) -> list[BaseTool]:
    """Resolve a persona's capability slugs to concrete tool objects.

    Unknown or unavailable slugs are silently skipped so a missing integration
    never breaks a conversation.
    """
    registry = _registry()
    resolved: list[BaseTool] = []
    for slug in tool_slugs or []:
        tool_obj = registry.get(slug)
        if tool_obj is not None:
            resolved.append(tool_obj)
        else:
            logger.debug(f"Persona requested unknown/unavailable tool slug: {slug}")
    return resolved


def all_tools() -> list[BaseTool]:
    """Every registered tool — used to build the graph's single ToolNode."""
    return list(_registry().values())
