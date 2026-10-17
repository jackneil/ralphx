"""Local API access token for the RalphX server.

The RalphX API can start Claude runs, read project files and manage the
stored Claude accounts. Every API request must therefore prove that it comes
from the user who owns the workspace.

The proof is a random token. The server creates the token at first start and
keeps it in ``<workspace>/api_token`` with owner-only permissions (0600).
A process that can read that file is the workspace owner.

The dashboard gets the token one time from the login URL that
``ralphx serve`` prints (``/?token=...``). The dashboard sends the token to
``POST /api/session`` and the server sets an HttpOnly, SameSite=Strict cookie.

Set ``RALPHX_API_TOKEN`` to supply the token from the environment instead of
the file. The value must be at least ``MIN_TOKEN_LENGTH`` characters.
"""

from __future__ import annotations

import hmac
import os
import secrets
import stat
import threading
from pathlib import Path
from typing import Optional

from ralphx.core.workspace import get_workspace_path

TOKEN_FILE_NAME = "api_token"
TOKEN_ENV_VAR = "RALPHX_API_TOKEN"
MIN_TOKEN_LENGTH = 32

_lock = threading.Lock()
# Cache: token file path -> (mtime_ns, token)
_cache: dict[str, tuple[int, str]] = {}


class APITokenError(RuntimeError):
    """The API token is missing, too short or cannot be stored safely."""


def get_api_token_path() -> Path:
    """Return the path of the token file in the active workspace."""
    return get_workspace_path() / TOKEN_FILE_NAME


def _validate(token: str, source: str) -> str:
    token = token.strip()
    if len(token) < MIN_TOKEN_LENGTH:
        raise APITokenError(
            f"The RalphX API token from {source} is shorter than "
            f"{MIN_TOKEN_LENGTH} characters. Refusing to use a weak token."
        )
    return token


def _create_token_file(path: Path) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    token = secrets.token_urlsafe(32)
    # O_EXCL: never overwrite a token that another process wrote first.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(fd, token.encode("ascii"))
    finally:
        os.close(fd)


def _read_token_file(path: Path) -> str:
    st = path.stat()
    if os.name == "posix" and stat.S_IMODE(st.st_mode) & 0o077:
        # Repair loose permissions before the token is trusted.
        os.chmod(path, 0o600)
    return _validate(path.read_text(encoding="ascii"), str(path))


def get_api_token() -> str:
    """Return the API token. Create the token file if it does not exist.

    Raises:
        APITokenError: The token is too short or the file cannot be created.
    """
    env_token = os.environ.get(TOKEN_ENV_VAR)
    if env_token is not None:
        return _validate(env_token, f"${TOKEN_ENV_VAR}")

    path = get_api_token_path()
    key = str(path)
    with _lock:
        try:
            if not path.exists():
                try:
                    _create_token_file(path)
                except FileExistsError:
                    pass
            mtime = path.stat().st_mtime_ns
            cached = _cache.get(key)
            if cached and cached[0] == mtime:
                return cached[1]
            token = _read_token_file(path)
        except OSError as exc:
            raise APITokenError(f"Cannot create or read the RalphX API token at {path}: {exc}") from exc
        _cache[key] = (mtime, token)
        return token


def token_matches(candidate: Optional[str]) -> bool:
    """Return True if ``candidate`` is the API token (constant-time compare)."""
    if not candidate:
        return False
    try:
        expected = get_api_token()
    except APITokenError:
        return False
    return hmac.compare_digest(candidate.encode("utf-8"), expected.encode("utf-8"))


def dashboard_login_url(host: str, port: int) -> str:
    """Return the one-time login URL for the dashboard."""
    display_host = "127.0.0.1" if host in ("0.0.0.0", "::", "") else host
    if ":" in display_host and not display_host.startswith("["):
        display_host = f"[{display_host}]"
    return f"http://{display_host}:{port}/?token={get_api_token()}"
