"""Jira Cloud REST client — minimal async wrapper over the v3 API.

Uses Basic auth with a single shared API token (``JIRA_EMAIL:JIRA_API_TOKEN``).
Because the token belongs to one service account, JQL ``currentUser()`` would
always resolve to *that* account — so to fetch "my tasks" for the person
chatting we first resolve their email to a Jira ``accountId`` and filter on it.

Only the read paths needed for the ``jira_my_tasks`` tool are implemented.
"""

from __future__ import annotations

import aiohttp
from loguru import logger

from philoagents.config import settings


class JiraError(Exception):
    """Raised for any non-recoverable Jira API problem (auth, network, etc.)."""


class JiraNotConfiguredError(JiraError):
    """Raised when Jira credentials are missing."""


class JiraClient:
    """Thin async Jira Cloud client. Create one per request and use as a context
    manager so the underlying aiohttp session is always closed."""

    def __init__(
        self,
        base_url: str | None = None,
        email: str | None = None,
        api_token: str | None = None,
        timeout_seconds: float = 15.0,
    ) -> None:
        self._base_url = (base_url or settings.JIRA_BASE_URL or "").rstrip("/")
        self._email = email or settings.JIRA_EMAIL
        self._api_token = api_token or settings.JIRA_API_TOKEN
        if not (self._base_url and self._email and self._api_token):
            raise JiraNotConfiguredError("Jira credentials are not configured.")
        self._timeout = aiohttp.ClientTimeout(total=timeout_seconds)
        self._session: aiohttp.ClientSession | None = None

    async def __aenter__(self) -> "JiraClient":
        self._session = aiohttp.ClientSession(
            auth=aiohttp.BasicAuth(self._email, self._api_token),
            timeout=self._timeout,
            headers={"Accept": "application/json"},
        )
        return self

    async def __aexit__(self, *_exc) -> None:
        if self._session:
            await self._session.close()

    # ------------------------------------------------------------------
    # Internal request helper
    # ------------------------------------------------------------------

    async def _get(self, path: str, params: dict | None = None) -> dict:
        assert self._session is not None, "JiraClient must be used as a context manager"
        url = f"{self._base_url}{path}"
        async with self._session.get(url, params=params) as resp:
            if resp.status == 401:
                raise JiraError("Jira authentication failed (check email / API token).")
            if resp.status >= 400:
                body = await resp.text()
                logger.warning(f"Jira GET {path} -> {resp.status}: {body[:300]}")
                raise JiraError(f"Jira request failed with status {resp.status}.")
            return await resp.json()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def resolve_account_id(self, email: str) -> str | None:
        """Return the Jira accountId for a user email, or None if not found."""
        results = await self._get("/rest/api/3/user/search", params={"query": email})
        for user in results or []:
            if (user.get("emailAddress") or "").lower() == email.lower():
                return user.get("accountId")
        # Fall back to the first match (some sites hide emails via privacy settings).
        if results:
            return results[0].get("accountId")
        return None

    async def get_issues_for(
        self,
        email: str,
        status: str | None = None,
        max_results: int = 20,
    ) -> list[dict]:
        """Return issues assigned to the given user email, newest first.

        Each issue is trimmed to a small, prompt-friendly shape.
        """
        account_id = await self.resolve_account_id(email)
        if not account_id:
            return []

        jql = f'assignee = "{account_id}"'
        if status:
            # Escape any embedded quotes in the user-provided status value.
            safe_status = status.replace('"', '\\"')
            jql += f' AND status = "{safe_status}"'
        jql += " ORDER BY updated DESC"

        data = await self._get(
            "/rest/api/3/search",
            params={
                "jql": jql,
                "maxResults": max_results,
                "fields": "summary,status,priority,duedate",
            },
        )

        issues: list[dict] = []
        for issue in data.get("issues", []):
            fields = issue.get("fields", {})
            issues.append(
                {
                    "key": issue.get("key"),
                    "summary": fields.get("summary"),
                    "status": (fields.get("status") or {}).get("name"),
                    "priority": (fields.get("priority") or {}).get("name"),
                    "duedate": fields.get("duedate"),
                    "url": f"{self._base_url}/browse/{issue.get('key')}",
                }
            )
        return issues
