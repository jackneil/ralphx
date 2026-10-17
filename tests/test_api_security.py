"""Security tests for the local API guard (GitHub issue #2).

Each test here fails on the code before the fix:
- the API had no authentication,
- CORS allowed every origin with credentials,
- there was no Host check (DNS rebinding),
- GET /api/auth/credentials/export returned the stored Claude OAuth tokens,
- GET /api/auth/flow/{id} returned the raw OAuth token response.
"""

import asyncio
import logging
import os
import stat
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from tests.conftest import TEST_API_TOKEN, make_api_client


def anon_client(**kwargs):
    """A client on a loopback Host, with no token."""
    from ralphx.api.main import app

    return TestClient(app, base_url="http://127.0.0.1:8765", **kwargs)


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------


class TestTokenRequired:
    @pytest.mark.parametrize(
        "method,path",
        [
            ("GET", "/api/projects"),
            ("GET", "/api/auth/accounts"),
            ("GET", "/api/auth/status"),
            ("GET", "/api/filesystem/browse"),
            ("GET", "/api/logs"),
            ("GET", "/api"),
            ("POST", "/api/projects"),
            ("POST", "/api/auth/accounts/reorder"),
            ("GET", "/api/session"),
            ("GET", "/openapi.json"),
            ("GET", "/docs"),
        ],
    )
    def test_anonymous_request_is_refused(self, method, path):
        response = anon_client().request(method, path)
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "unauthorized"

    def test_wrong_token_is_refused(self):
        client = anon_client(headers={"Authorization": "Bearer " + "x" * 40})
        assert client.get("/api/projects").status_code == 401

    def test_bearer_token_is_accepted(self):
        client = anon_client(headers={"Authorization": f"Bearer {TEST_API_TOKEN}"})
        assert client.get("/api/projects").status_code == 200

    def test_token_header_is_accepted(self):
        client = anon_client(headers={"X-RalphX-Token": TEST_API_TOKEN})
        assert client.get("/api/projects").status_code == 200

    def test_cookie_is_accepted(self):
        client = anon_client()
        client.cookies.set("ralphx_token", TEST_API_TOKEN)
        assert client.get("/api/projects").status_code == 200

    def test_query_string_token_is_not_accepted(self):
        # A token in the URL leaks into logs and history; only the dashboard
        # bootstrap reads it, and only to POST it to /api/session.
        assert anon_client().get(f"/api/projects?token={TEST_API_TOKEN}").status_code == 401

    def test_health_is_public(self):
        response = anon_client().get("/api/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"

    def test_spa_shell_is_public(self):
        # The login screen itself must load without a token.
        response = anon_client().get("/")
        assert response.status_code in (200, 404)
        assert response.status_code != 401


class TestSession:
    def test_wrong_token_does_not_log_in(self):
        client = anon_client()
        response = client.post("/api/session", json={"token": "nope" * 10})
        assert response.status_code == 401
        assert "ralphx_token" not in response.headers.get("set-cookie", "")

    def test_login_sets_strict_httponly_cookie_and_logout_clears_it(self):
        client = anon_client()
        response = client.post("/api/session", json={"token": TEST_API_TOKEN})
        assert response.status_code == 200
        cookie = response.headers["set-cookie"].lower()
        assert "ralphx_token=" in cookie
        assert "httponly" in cookie
        assert "samesite=strict" in cookie
        assert "path=/" in cookie

        assert client.get("/api/session").status_code == 200
        assert client.get("/api/projects").status_code == 200

        response = client.delete("/api/session")
        assert response.status_code == 200
        client.cookies.clear()
        assert client.get("/api/projects").status_code == 401


# ---------------------------------------------------------------------------
# Browser attacks: cross-origin pages and DNS rebinding
# ---------------------------------------------------------------------------


class TestCrossOrigin:
    def test_no_wildcard_cors_header(self):
        client = make_api_client()
        response = client.get("/api/health", headers={"Origin": "https://evil.example"})
        assert "access-control-allow-origin" not in response.headers
        assert "access-control-allow-credentials" not in response.headers

    def test_cors_preflight_is_not_granted(self):
        response = anon_client().options(
            "/api/auth/accounts",
            headers={
                "Origin": "https://evil.example",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert "access-control-allow-origin" not in response.headers
        assert response.status_code >= 400

    def test_cross_origin_request_is_refused_even_with_cookie(self):
        client = anon_client()
        client.cookies.set("ralphx_token", TEST_API_TOKEN)
        response = client.get("/api/projects", headers={"Origin": "https://evil.example"})
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "invalid_origin"

    def test_null_origin_is_refused(self):
        response = make_api_client().post("/api/projects", json={}, headers={"Origin": "null"})
        assert response.status_code == 403

    def test_cross_site_fetch_metadata_is_refused(self):
        client = make_api_client()
        response = client.get("/api/projects", headers={"Sec-Fetch-Site": "cross-site"})
        assert response.status_code == 403

    def test_other_localhost_port_is_refused(self):
        client = make_api_client()
        response = client.get(
            "/api/projects",
            headers={"Origin": "http://127.0.0.1:3000", "Sec-Fetch-Site": "same-site"},
        )
        assert response.status_code == 403

    def test_same_origin_request_is_allowed(self):
        client = make_api_client()
        response = client.get(
            "/api/projects",
            headers={"Origin": "http://127.0.0.1", "Sec-Fetch-Site": "same-origin"},
        )
        assert response.status_code == 200

    def test_configured_dev_origin_is_allowed(self, monkeypatch):
        monkeypatch.setenv("RALPHX_ALLOWED_ORIGINS", "http://localhost:16768")
        client = make_api_client()
        response = client.post(
            "/api/session",
            json={"token": TEST_API_TOKEN},
            headers={"Origin": "http://localhost:16768"},
        )
        assert response.status_code == 200


class TestHostCheck:
    @pytest.mark.parametrize("host", ["evil.example", "evil.example:8765", "127.0.0.1.evil.example", ""])
    def test_rebinding_host_is_refused_even_with_token(self, host):
        client = make_api_client()
        response = client.get("/api/projects", headers={"Host": host})
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "invalid_host"

    def test_rebinding_host_cannot_load_the_spa(self):
        assert anon_client().get("/", headers={"Host": "evil.example"}).status_code == 400

    @pytest.mark.parametrize("host", ["127.0.0.1:8765", "localhost:16767", "[::1]:8765", "localhost"])
    def test_loopback_hosts_are_allowed(self, host):
        response = make_api_client().get("/api/projects", headers={"Host": host})
        assert response.status_code == 200

    def test_configured_host_is_allowed(self, monkeypatch):
        monkeypatch.setenv("RALPHX_ALLOWED_HOSTS", "box.local")
        response = make_api_client().get("/api/projects", headers={"Host": "box.local:8765"})
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# Token exposure
# ---------------------------------------------------------------------------


class TestNoTokenExport:
    def test_credentials_export_endpoint_is_gone(self):
        client = make_api_client()
        for path in ("/api/auth/credentials/export", "/api/credentials/export"):
            response = client.get(path)
            assert response.status_code == 404, path
            assert "accessToken" not in response.text

    def test_flow_status_never_returns_oauth_tokens(self):
        from ralphx.api.routes import auth as auth_routes

        async def done():
            return {
                "success": True,
                "tokens": {"access_token": "sk-ant-oat-secret", "refresh_token": "sk-ant-ort-secret"},
            }

        loop = asyncio.new_event_loop()
        try:
            task = loop.create_task(done())
            loop.run_until_complete(task)
        finally:
            loop.close()
        auth_routes._active_flows["flow-test"] = task
        try:
            response = make_api_client().get("/api/auth/flow/flow-test")
        finally:
            auth_routes._active_flows.pop("flow-test", None)
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "completed"
        assert body["result"] == {"success": True}
        assert "secret" not in response.text


# ---------------------------------------------------------------------------
# Token storage and boot guard
# ---------------------------------------------------------------------------


class TestTokenFile:
    def test_token_file_is_created_owner_only_and_reused(self, monkeypatch, tmp_path):
        from ralphx.core import api_auth

        monkeypatch.delenv("RALPHX_API_TOKEN")
        monkeypatch.setenv("RALPHX_HOME", str(tmp_path / "home"))
        token = api_auth.get_api_token()
        path = tmp_path / "home" / "api_token"
        assert path.read_text() == token
        assert len(token) >= api_auth.MIN_TOKEN_LENGTH
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
        assert api_auth.get_api_token() == token

    def test_loose_permissions_are_repaired(self, monkeypatch, tmp_path):
        from ralphx.core import api_auth

        monkeypatch.delenv("RALPHX_API_TOKEN")
        monkeypatch.setenv("RALPHX_HOME", str(tmp_path))
        path = tmp_path / "api_token"
        path.write_text("a" * 43)
        os.chmod(path, 0o644)
        assert api_auth.get_api_token() == "a" * 43
        assert stat.S_IMODE(path.stat().st_mode) == 0o600

    def test_short_token_file_is_refused(self, monkeypatch, tmp_path):
        from ralphx.core import api_auth

        monkeypatch.delenv("RALPHX_API_TOKEN")
        monkeypatch.setenv("RALPHX_HOME", str(tmp_path))
        (tmp_path / "api_token").write_text("short")
        with pytest.raises(api_auth.APITokenError):
            api_auth.get_api_token()
        # The guard fails closed: a broken token file lets nobody in.
        assert anon_client(headers={"Authorization": "Bearer short"}).get("/api/projects").status_code == 401

    def test_short_env_token_is_refused(self, monkeypatch):
        from ralphx.core import api_auth

        monkeypatch.setenv("RALPHX_API_TOKEN", "changeme")
        with pytest.raises(api_auth.APITokenError):
            api_auth.get_api_token()

    def test_server_refuses_to_start_with_a_weak_token(self, monkeypatch):
        from ralphx.core.api_auth import APITokenError

        monkeypatch.setenv("RALPHX_API_TOKEN", "changeme")
        with pytest.raises(APITokenError):
            with make_api_client():
                pass


class TestPrivateFiles:
    def test_workspace_directory_is_owner_only(self, monkeypatch, tmp_path):
        from ralphx.core.workspace import ensure_workspace

        home = tmp_path / "ws"
        home.mkdir(mode=0o755)
        monkeypatch.setenv("RALPHX_HOME", str(home))
        ensure_workspace()
        assert stat.S_IMODE(home.stat().st_mode) == 0o700

    def test_server_log_is_in_the_workspace_and_owner_only(self):
        from ralphx.api import main

        assert not str(main.LOG_FILE).startswith("/tmp/")
        assert stat.S_IMODE(main.LOG_FILE.stat().st_mode) == 0o600

    def test_swapped_credentials_file_is_never_world_readable(self, tmp_path):
        from ralphx.core.auth import _write_private_file

        target = tmp_path / ".credentials.json"
        old_umask = os.umask(0)
        try:
            _write_private_file(target, '{"claudeAiOauth": {}}')
        finally:
            os.umask(old_umask)
        assert stat.S_IMODE(target.stat().st_mode) == 0o600
        assert target.read_text() == '{"claudeAiOauth": {}}'

    def test_oauth_callback_does_not_log_the_code(self, caplog):
        from ralphx.core.oauth import OAuthFlow

        flow = OAuthFlow()
        flow._state = "expected-state"
        flow._event = asyncio.Event()
        request = SimpleNamespace(query={"code": "auth-code-secret", "state": "other"})
        with caplog.at_level(logging.INFO, logger="ralphx.oauth"):
            asyncio.run(flow._handle_callback(request))
        assert "auth-code-secret" not in caplog.text
        assert "code" in caplog.text


# ---------------------------------------------------------------------------
# `ralphx serve` bind guard
# ---------------------------------------------------------------------------


class TestServeBindGuard:
    def _run(self, args):
        from ralphx.cli import app

        with patch("uvicorn.run") as run:
            result = CliRunner().invoke(app, ["serve", *args])
        return result, run

    def test_loopback_default_starts_and_prints_login_link(self):
        result, run = self._run([])
        assert result.exit_code == 0, result.output
        run.assert_called_once()
        assert run.call_args.kwargs["host"] == "127.0.0.1"
        assert f"/?token={TEST_API_TOKEN}" in result.output

    @pytest.mark.parametrize("host", ["0.0.0.0", "192.168.1.20", "::"])
    def test_non_loopback_host_is_refused_without_flag(self, host):
        result, run = self._run(["--host", host])
        assert result.exit_code != 0
        run.assert_not_called()

    def test_wildcard_needs_allowed_host(self):
        result, run = self._run(["--host", "0.0.0.0", "--allow-remote"])
        assert result.exit_code != 0
        run.assert_not_called()

    def test_allow_remote_with_allowed_host_starts(self, monkeypatch):
        monkeypatch.setenv("RALPHX_ALLOWED_HOSTS", "")
        result, run = self._run(["--host", "0.0.0.0", "--allow-remote", "--allowed-host", "box.local"])
        assert result.exit_code == 0, result.output
        run.assert_called_once()
        assert "box.local" in os.environ["RALPHX_ALLOWED_HOSTS"].split(",")
