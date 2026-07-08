"""OAuth 2.0 / OpenID Connect helpers for Google and Slack sign-in.

Uses the standard Authorization Code flow with httpx (no extra deps):

    /auth/{provider}/login    -> redirect user to the provider
    provider consent screen   -> redirects back to
    /auth/{provider}/callback -> exchange code, fetch profile, issue our JWT
"""

from urllib.parse import urlencode

import httpx

from philoagents.config import settings

PROVIDERS = {
    "google": {
        "authorize_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "userinfo_url": "https://www.googleapis.com/oauth2/v2/userinfo",
        "scope": "openid email profile",
    },
    "slack": {
        "authorize_url": "https://slack.com/openid/connect/authorize",
        "token_url": "https://slack.com/api/openid.connect.token",
        "userinfo_url": "https://slack.com/api/openid.connect.userInfo",
        "scope": "openid email profile",
    },
}


def get_credentials(provider: str) -> tuple[str | None, str | None]:
    if provider == "google":
        return settings.GOOGLE_CLIENT_ID, settings.GOOGLE_CLIENT_SECRET
    if provider == "slack":
        return settings.SLACK_CLIENT_ID, settings.SLACK_CLIENT_SECRET
    return None, None


def is_supported(provider: str) -> bool:
    return provider in PROVIDERS


def is_configured(provider: str) -> bool:
    client_id, client_secret = get_credentials(provider)
    return bool(client_id and client_secret)


def redirect_uri(provider: str) -> str:
    return f"{settings.OAUTH_REDIRECT_BASE}/auth/{provider}/callback"


def build_authorize_url(provider: str, state: str) -> str:
    cfg = PROVIDERS[provider]
    client_id, _ = get_credentials(provider)
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri(provider),
        "response_type": "code",
        "scope": cfg["scope"],
        "state": state,
    }
    if provider == "google":
        params["access_type"] = "offline"
        params["prompt"] = "select_account"
    return f"{cfg['authorize_url']}?{urlencode(params)}"


async def exchange_code_for_userinfo(provider: str, code: str) -> dict:
    """Trade the authorization code for the user's profile.

    Returns a dict with ``email`` and ``name``.
    """
    cfg = PROVIDERS[provider]
    client_id, client_secret = get_credentials(provider)
    data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": redirect_uri(provider),
    }

    async with httpx.AsyncClient(timeout=15) as client:
        token_res = await client.post(cfg["token_url"], data=data)
        token_res.raise_for_status()
        token_json = token_res.json()
        access_token = token_json.get("access_token")
        if not access_token:
            raise RuntimeError(
                f"{provider} did not return an access token: {token_json}"
            )

        info_res = await client.get(
            cfg["userinfo_url"],
            headers={"Authorization": f"Bearer {access_token}"},
        )
        info_res.raise_for_status()
        info = info_res.json()

    email = info.get("email")
    name = info.get("name") or info.get("given_name") or ""
    if not email:
        raise RuntimeError(f"{provider} profile did not include an email address.")
    return {"email": email, "name": name}
