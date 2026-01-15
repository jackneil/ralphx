"""OAuth PKCE flow for Claude subscription authentication."""

import asyncio
import base64
import hashlib
import secrets
import webbrowser
from urllib.parse import urlencode

import httpx
from aiohttp import web

CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
AUTH_URL = "https://claude.ai/oauth/authorize"
TOKEN_URL = "https://console.anthropic.com/v1/oauth/token"
SCOPES = "org:create_api_key user:profile user:inference user:sessions:claude_code"


def generate_pkce() -> tuple[str, str]:
    """Generate PKCE verifier and challenge."""
    verifier = secrets.token_urlsafe(32)
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).rstrip(b"=").decode()
    return verifier, challenge


class OAuthFlow:
    """Handles OAuth authentication with local callback server."""

    def __init__(self):
        self._verifier: str | None = None
        self._state: str | None = None
        self._redirect_uri: str | None = None
        self._result: dict | None = None
        self._event = asyncio.Event()

    async def start(self) -> dict:
        """Start OAuth flow: opens browser and waits for callback."""
        self._verifier, challenge = generate_pkce()
        self._state = secrets.token_urlsafe(32)

        # Start callback server
        app = web.Application()
        app.router.add_get("/callback", self._handle_callback)
        runner = web.AppRunner(app)
        await runner.setup()

        # Find available port
        port = None
        for p in range(45100, 45200):
            try:
                site = web.TCPSite(runner, "localhost", p)
                await site.start()
                port = p
                break
            except OSError:
                continue

        if port is None:
            await runner.cleanup()
            return {"error": "No available port for callback server"}

        self._redirect_uri = f"http://localhost:{port}/callback"

        # Build auth URL - note: code=true is required!
        params = {
            "code": "true",
            "client_id": CLIENT_ID,
            "response_type": "code",
            "redirect_uri": self._redirect_uri,
            "scope": SCOPES,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": self._state,
        }
        auth_url = f"{AUTH_URL}?{urlencode(params)}"

        # Open browser
        webbrowser.open(auth_url)

        # Wait for callback (timeout 5 min)
        try:
            await asyncio.wait_for(self._event.wait(), timeout=300)
        finally:
            await runner.cleanup()

        return self._result or {"error": "No result received"}

    async def _handle_callback(self, request: web.Request) -> web.Response:
        """Handle OAuth callback."""
        code = request.query.get("code")
        state = request.query.get("state")
        error = request.query.get("error")

        if error:
            self._result = {"error": error}
            self._event.set()
            return web.Response(
                text="<h1>Error</h1><p>Authentication failed.</p>",
                content_type="text/html",
            )

        # CSRF protection: validate state matches what we sent
        if state != self._state:
            self._result = {"error": "Invalid state parameter (possible CSRF attack)"}
            self._event.set()
            return web.Response(
                text="<h1>Error</h1><p>Security validation failed.</p>",
                content_type="text/html",
            )

        if code:
            try:
                tokens = await self._exchange_code(code)
                self._result = {"success": True, "tokens": tokens}
            except Exception as e:
                self._result = {"error": str(e)}

        self._event.set()
        return web.Response(
            text="<h1>Success!</h1><p>You can close this window.</p><script>window.close()</script>",
            content_type="text/html",
        )

    async def _exchange_code(self, code: str) -> dict:
        """Exchange authorization code for tokens.

        The token response includes account info with email_address.
        """
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                TOKEN_URL,
                json={  # Must be JSON, not form data!
                    "grant_type": "authorization_code",
                    "code": code,
                    "state": self._state,
                    "client_id": CLIENT_ID,
                    "code_verifier": self._verifier,
                    "redirect_uri": self._redirect_uri,
                },
                headers={"Content-Type": "application/json"},
            )
            resp.raise_for_status()
            tokens = resp.json()

            # Extract email from account field in token response
            # Response format: {"account": {"uuid": "...", "email_address": "..."}, ...}
            account = tokens.get("account", {})
            if account.get("email_address"):
                tokens["email"] = account["email_address"]

            return tokens
