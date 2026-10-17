"""Request guard for the local RalphX API.

The guard runs before every route. It applies three checks:

1. Host check (all paths). The Host header must name a loopback address or a
   host in ``RALPHX_ALLOWED_HOSTS``. This stops DNS rebinding: a page on
   ``evil.example`` that resolves its own name to 127.0.0.1 still sends
   ``Host: evil.example``.
2. Origin check (all paths). A request that carries an ``Origin`` header must
   come from the same origin as the server, or from an origin in
   ``RALPHX_ALLOWED_ORIGINS``. A cross-site request to a protected path is
   refused even when it has no ``Origin`` header.
3. Token check (API and docs paths). The request must carry the API token in
   the ``ralphx_token`` cookie, an ``Authorization: Bearer`` header, or an
   ``X-RalphX-Token`` header.

The guard is a plain ASGI middleware so that it also covers streaming
responses (Server-Sent Events).
"""

from __future__ import annotations

import json
import logging
import os
from http.cookies import CookieError, SimpleCookie
from typing import Iterable, Optional

from ralphx.core.api_auth import token_matches

logger = logging.getLogger(__name__)

SESSION_COOKIE = "ralphx_token"
TOKEN_HEADER = "x-ralphx-token"

ALLOWED_HOSTS_ENV = "RALPHX_ALLOWED_HOSTS"
ALLOWED_ORIGINS_ENV = "RALPHX_ALLOWED_ORIGINS"

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})

# Paths that do not need the token.
# /api/health returns only the version. POST /api/session is the login that
# exchanges the token for the cookie. DELETE /api/session clears the cookie.
_PUBLIC_API = {
    ("/api/health", "GET"),
    ("/api/health", "HEAD"),
    ("/api/session", "POST"),
    ("/api/session", "DELETE"),
}


def _split_env(name: str) -> list[str]:
    raw = os.environ.get(name, "")
    return [part.strip() for part in raw.split(",") if part.strip()]


def allowed_hosts() -> set[str]:
    """Return the host names that the server answers to."""
    hosts = set(LOOPBACK_HOSTS)
    hosts.update(h.lower().strip("[]").rstrip(".") for h in _split_env(ALLOWED_HOSTS_ENV))
    return hosts


def allowed_extra_origins() -> set[str]:
    """Return the configured extra origins (for example the Vite dev server)."""
    return {o.rstrip("/").lower() for o in _split_env(ALLOWED_ORIGINS_ENV)}


def parse_host(host_header: str) -> Optional[str]:
    """Return the host name part of a Host header, lowercased, without port."""
    value = host_header.strip().lower()
    if not value:
        return None
    if value.startswith("["):
        end = value.find("]")
        if end == -1:
            return None
        return value[1:end]
    if value.count(":") == 1:
        value = value.split(":", 1)[0]
    elif value.count(":") > 1:
        # A bare IPv6 address without brackets is not a valid Host header.
        return None
    return value.rstrip(".") or None


def is_protected_path(path: str) -> bool:
    """Return True for paths that need the API token."""
    if path == "/api" or path.startswith("/api/"):
        return True
    return path in ("/docs", "/redoc", "/openapi.json") or path.startswith("/docs/")


def _headers(scope) -> dict[str, str]:
    result: dict[str, str] = {}
    for raw_name, raw_value in scope.get("headers", []):
        name = raw_name.decode("latin-1").lower()
        value = raw_value.decode("latin-1")
        if name == "cookie" and "cookie" in result:
            result[name] = result[name] + "; " + value
        else:
            result.setdefault(name, value)
    return result


def _cookie_token(cookie_header: Optional[str]) -> Optional[str]:
    if not cookie_header:
        return None
    jar = SimpleCookie()
    try:
        jar.load(cookie_header)
    except CookieError:
        return None
    morsel = jar.get(SESSION_COOKIE)
    return morsel.value if morsel else None


def request_tokens(headers: dict[str, str]) -> Iterable[str]:
    """Yield every token candidate that the request carries."""
    auth = headers.get("authorization", "")
    if auth[:7].lower() == "bearer ":
        yield auth[7:].strip()
    header_token = headers.get(TOKEN_HEADER)
    if header_token:
        yield header_token.strip()
    cookie = _cookie_token(headers.get("cookie"))
    if cookie:
        yield cookie


class LocalAccessGuard:
    """ASGI middleware that enforces the Host, Origin and token checks."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        headers = _headers(scope)
        path = scope.get("path", "")
        method = scope.get("method", "GET").upper()

        refusal = self._check(scope, headers, path, method)
        if refusal is not None:
            status, code, message = refusal
            # Log the reason in a values-free shape so it can be diagnosed.
            logger.warning(
                "Refused %s %s: %s (host=%s origin=%s sec_fetch_site=%s)",
                method,
                path,
                code,
                "present" if headers.get("host") else "missing",
                "present" if headers.get("origin") else "absent",
                headers.get("sec-fetch-site", "absent"),
            )
            if scope["type"] == "websocket":
                await send({"type": "websocket.close", "code": 1008})
                return
            body = json.dumps({"error": {"message": message, "code": code}}).encode()
            response_headers = [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
                (b"cache-control", b"no-store"),
            ]
            await send({"type": "http.response.start", "status": status, "headers": response_headers})
            await send({"type": "http.response.body", "body": body})
            return

        await self.app(scope, receive, send)

    def _check(self, scope, headers, path, method):
        host_header = headers.get("host", "")
        hostname = parse_host(host_header)
        if hostname is None or hostname not in allowed_hosts():
            return 400, "invalid_host", "Invalid Host header"

        scheme = scope.get("scheme", "http")
        if scope["type"] == "websocket":
            scheme = "https" if scheme == "wss" else "http"
        same_origin = f"{scheme}://{host_header.strip().lower()}"

        origin = headers.get("origin")
        origin_ok = False
        if origin is not None:
            normalized = origin.strip().rstrip("/").lower()
            origin_ok = normalized == same_origin or normalized in allowed_extra_origins()
            if not origin_ok:
                return 403, "invalid_origin", "Cross-origin request refused"

        protected = is_protected_path(path)
        if protected:
            fetch_site = headers.get("sec-fetch-site", "").lower()
            if fetch_site in ("cross-site", "same-site") and not origin_ok:
                return 403, "invalid_origin", "Cross-site request refused"

        if not protected or (path, method) in _PUBLIC_API:
            return None

        for candidate in request_tokens(headers):
            if token_matches(candidate):
                return None
        return (
            401,
            "unauthorized",
            "Authentication required. Open the login link that `ralphx serve` prints, "
            "or run `ralphx dashboard-url`.",
        )
