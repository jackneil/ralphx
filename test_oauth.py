#!/usr/bin/env python3
"""Test OAuth flow with Playwright to find working configuration."""

import asyncio
import base64
import hashlib
import secrets
import json
from urllib.parse import urlencode, urlparse, parse_qs

import httpx
from aiohttp import web
from playwright.async_api import async_playwright

CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"

# Different configurations to test
CONFIGS = [
    {
        "name": "claude.ai + platform token + create_api_key",
        "auth_url": "https://claude.ai/oauth/authorize",
        "token_url": "https://platform.claude.com/v1/oauth/token",
        "scopes": "org:create_api_key user:profile user:inference user:sessions:claude_code",
        "expires_in": None,  # Don't pass expires_in, use create_api_key instead
        "use_create_api_key": True,
    },
    {
        "name": "platform.claude.com auth + no scopes + expires_in",
        "auth_url": "https://platform.claude.com/oauth/authorize",
        "token_url": "https://platform.claude.com/v1/oauth/token",
        "scopes": "",
        "expires_in": 31536000,
        "use_create_api_key": False,
    },
    {
        "name": "claude.ai + inference only + expires_in",
        "auth_url": "https://claude.ai/oauth/authorize",
        "token_url": "https://platform.claude.com/v1/oauth/token",
        "scopes": "user:inference",
        "expires_in": 31536000,
        "use_create_api_key": False,
    },
]


def generate_pkce():
    """Generate PKCE verifier and challenge."""
    verifier = secrets.token_urlsafe(32)
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).rstrip(b"=").decode()
    return verifier, challenge


async def test_config(config: dict, headless: bool = False):
    """Test a single OAuth configuration."""
    print(f"\n{'='*60}")
    print(f"Testing: {config['name']}")
    print(f"{'='*60}")

    verifier, challenge = generate_pkce()
    state = secrets.token_urlsafe(32)

    # Result storage
    result = {"code": None, "error": None}
    event = asyncio.Event()

    # Callback handler
    async def handle_callback(request):
        code = request.query.get("code")
        error = request.query.get("error")
        recv_state = request.query.get("state")

        if error:
            result["error"] = error
            print(f"  OAuth error: {error}")
        elif recv_state != state:
            result["error"] = "State mismatch"
            print(f"  State mismatch!")
        else:
            result["code"] = code
            print(f"  Got authorization code!")

        event.set()
        return web.Response(
            text="<h1>Done!</h1><p>You can close this window.</p><script>window.close()</script>",
            content_type="text/html",
        )

    # Start callback server
    app = web.Application()
    app.router.add_get("/callback", handle_callback)
    runner = web.AppRunner(app)
    await runner.setup()

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
        print("  ERROR: No available port")
        await runner.cleanup()
        return None

    redirect_uri = f"http://localhost:{port}/callback"
    print(f"  Callback server on port {port}")

    # Build auth URL
    params = {
        "code": "true",
        "client_id": CLIENT_ID,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": state,
    }
    if config["scopes"]:
        params["scope"] = config["scopes"]

    auth_url = f"{config['auth_url']}?{urlencode(params)}"
    print(f"  Auth URL: {config['auth_url']}")
    print(f"  Scopes: {config['scopes'] or '(none)'}")

    # Open browser
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context()
        page = await context.new_page()

        print(f"  Opening browser...")
        await page.goto(auth_url)

        # Wait for callback or timeout
        print(f"  Waiting for login (60s timeout)...")
        try:
            await asyncio.wait_for(event.wait(), timeout=60)
        except asyncio.TimeoutError:
            print(f"  Timeout waiting for callback")
            await browser.close()
            await runner.cleanup()
            return None

        await browser.close()

    await runner.cleanup()

    if result["error"]:
        print(f"  OAuth failed: {result['error']}")
        return None

    if not result["code"]:
        print(f"  No code received")
        return None

    # Token exchange
    print(f"  Exchanging code for token...")
    token_body = {
        "grant_type": "authorization_code",
        "code": result["code"],
        "state": state,
        "client_id": CLIENT_ID,
        "code_verifier": verifier,
        "redirect_uri": redirect_uri,
    }
    if config["expires_in"]:
        token_body["expires_in"] = config["expires_in"]

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            config["token_url"],
            json=token_body,
            headers={"Content-Type": "application/json"},
        )

        print(f"  Token response: HTTP {resp.status_code}")
        if resp.status_code != 200:
            print(f"  Error: {resp.text}")
            return None

        tokens = resp.json()
        print(f"  expires_in: {tokens.get('expires_in')} seconds ({tokens.get('expires_in', 0) / 86400:.1f} days)")
        print(f"  scopes: {tokens.get('scope')}")
        print(f"  has refresh_token: {bool(tokens.get('refresh_token'))}")

        # Try create_api_key if configured
        if config["use_create_api_key"] and "org:create_api_key" in tokens.get("scope", ""):
            print(f"  Calling create_api_key endpoint...")
            api_resp = await client.post(
                "https://api.anthropic.com/api/oauth/claude_cli/create_api_key",
                headers={
                    "Authorization": f"Bearer {tokens['access_token']}",
                    "Content-Type": "application/json",
                },
                json={},
            )
            print(f"  create_api_key response: HTTP {api_resp.status_code}")
            if api_resp.status_code == 200:
                api_data = api_resp.json()
                print(f"  API key data keys: {list(api_data.keys())}")
                print(f"  SUCCESS! Got long-lived API key!")
                return {"tokens": tokens, "api_key": api_data}
            else:
                print(f"  Error: {api_resp.text}")

        return {"tokens": tokens}


async def main():
    print("OAuth Long-Lived Token Test")
    print("You'll need to log in via the browser for each test.")

    # Test first config (most likely to work based on Claude Code analysis)
    config = CONFIGS[0]
    result = await test_config(config, headless=False)

    if result:
        print(f"\n{'='*60}")
        print("SUCCESS!")
        print(f"{'='*60}")
        print(json.dumps(result, indent=2, default=str))
    else:
        print(f"\n{'='*60}")
        print("FAILED - Try next config?")
        print(f"{'='*60}")


if __name__ == "__main__":
    asyncio.run(main())
