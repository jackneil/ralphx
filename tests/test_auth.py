"""Tests for RalphX OAuth credential management.

Tests the complete credential flow:
- store_oauth_tokens() with all fields including new OAuth metadata
- swap_credentials_for_loop() writing correct JSON format to .credentials.json
- Backwards compatibility with credentials missing new fields
- Migration v6 adding new columns
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
import time

import pytest

from ralphx.core.database import Database
from ralphx.core.auth import (
    store_oauth_tokens,
    swap_credentials_for_loop,
    CLAUDE_CREDENTIALS_PATH,
)


@pytest.fixture
def db():
    """Create an in-memory database for testing."""
    database = Database(":memory:")
    yield database
    database.close()


@pytest.fixture
def mock_credentials_path(tmp_path):
    """Mock the Claude credentials path to a temp directory."""
    creds_path = tmp_path / ".claude" / ".credentials.json"
    backup_path = tmp_path / ".claude" / ".credentials.backup.json"
    lock_path = tmp_path / ".claude" / ".credentials.lock"

    with patch("ralphx.core.auth.CLAUDE_CREDENTIALS_PATH", creds_path), \
         patch("ralphx.core.auth.CLAUDE_CREDENTIALS_BACKUP", backup_path), \
         patch("ralphx.core.auth.CREDENTIAL_LOCK_PATH", lock_path):
        yield creds_path


class TestStoreOAuthTokens:
    """Test store_oauth_tokens() with all credential fields."""

    def test_store_tokens_with_all_fields(self, db):
        """Test storing tokens with all new OAuth metadata fields."""
        tokens = {
            "access_token": "sk-ant-oat01-test-token",
            "refresh_token": "sk-ant-ort01-test-refresh",
            "expires_in": 28800,
            "email": "user@example.com",
            "scopes": ["user:inference", "user:profile", "user:sessions:claude_code"],
            "subscription_type": "max",
            "rate_limit_tier": "default_claude_max_20x",
        }

        with patch("ralphx.core.auth.Database", return_value=db):
            result = store_oauth_tokens(tokens, scope="global")

        assert result is True

        # Verify stored in database
        creds = db.get_credentials()
        assert creds is not None
        assert creds["access_token"] == "sk-ant-oat01-test-token"
        assert creds["refresh_token"] == "sk-ant-ort01-test-refresh"
        assert creds["email"] == "user@example.com"
        # Scopes are stored as JSON string
        assert json.loads(creds["scopes"]) == ["user:inference", "user:profile", "user:sessions:claude_code"]
        assert creds["subscription_type"] == "max"
        assert creds["rate_limit_tier"] == "default_claude_max_20x"

    def test_store_tokens_minimal_fields(self, db):
        """Test storing tokens with only required fields (backwards compatibility)."""
        tokens = {
            "access_token": "sk-ant-oat01-minimal",
            "expires_in": 28800,
        }

        with patch("ralphx.core.auth.Database", return_value=db):
            result = store_oauth_tokens(tokens, scope="global")

        assert result is True

        creds = db.get_credentials()
        assert creds is not None
        assert creds["access_token"] == "sk-ant-oat01-minimal"
        # Optional fields should be None
        assert creds["refresh_token"] is None
        assert creds["email"] is None
        assert creds["scopes"] is None
        assert creds["subscription_type"] is None
        assert creds["rate_limit_tier"] is None


class TestSwapCredentialsForLoop:
    """Test swap_credentials_for_loop() writes correct JSON format."""

    def test_swap_writes_all_six_fields(self, db, mock_credentials_path):
        """Test that swap_credentials_for_loop writes all 6 required fields."""
        # Store credentials with all fields
        expires_at = int(time.time()) + 28800
        db.store_credentials(
            scope="global",
            access_token="sk-ant-oat01-test",
            refresh_token="sk-ant-ort01-test",
            expires_at=expires_at,
            email="user@example.com",
            scopes=json.dumps(["user:inference", "user:profile"]),
            subscription_type="max",
            rate_limit_tier="default_claude_max_20x",
        )

        with patch("ralphx.core.auth.Database", return_value=db):
            with swap_credentials_for_loop() as has_creds:
                assert has_creds is True

                # Verify JSON was written correctly
                assert mock_credentials_path.exists()
                written_data = json.loads(mock_credentials_path.read_text())

                oauth = written_data.get("claudeAiOauth", {})

                # Verify all 6 fields
                assert oauth["accessToken"] == "sk-ant-oat01-test"
                assert oauth["refreshToken"] == "sk-ant-ort01-test"
                assert oauth["expiresAt"] == expires_at * 1000  # Milliseconds
                assert oauth["scopes"] == ["user:inference", "user:profile"]
                assert oauth["subscriptionType"] == "max"
                assert oauth["rateLimitTier"] == "default_claude_max_20x"

    def test_swap_uses_defaults_for_missing_fields(self, db, mock_credentials_path):
        """Test backwards compatibility: uses defaults when fields are missing."""
        # Store credentials WITHOUT new fields (simulates pre-migration data)
        expires_at = int(time.time()) + 28800
        db.store_credentials(
            scope="global",
            access_token="sk-ant-oat01-old",
            refresh_token="sk-ant-ort01-old",
            expires_at=expires_at,
            email=None,  # Explicitly no email
            # Note: NOT passing scopes, subscription_type, rate_limit_tier
        )

        with patch("ralphx.core.auth.Database", return_value=db):
            with swap_credentials_for_loop() as has_creds:
                assert has_creds is True

                written_data = json.loads(mock_credentials_path.read_text())
                oauth = written_data.get("claudeAiOauth", {})

                # Should use defaults
                assert oauth["scopes"] == ["user:inference", "user:profile", "user:sessions:claude_code"]
                assert oauth["subscriptionType"] == "max"
                assert oauth["rateLimitTier"] == "default_claude_max_20x"

    def test_swap_handles_malformed_scopes_json(self, db, mock_credentials_path):
        """Test graceful handling of malformed JSON in scopes field."""
        expires_at = int(time.time()) + 28800

        # Manually insert with malformed scopes JSON
        with db._writer() as conn:
            conn.execute(
                """INSERT INTO credentials
                   (scope, access_token, expires_at, scopes)
                   VALUES (?, ?, ?, ?)""",
                ("global", "sk-ant-oat01-test", expires_at, "not-valid-json{{{")
            )

        with patch("ralphx.core.auth.Database", return_value=db):
            with swap_credentials_for_loop() as has_creds:
                assert has_creds is True

                written_data = json.loads(mock_credentials_path.read_text())
                oauth = written_data.get("claudeAiOauth", {})

                # Should fall back to default scopes
                assert oauth["scopes"] == ["user:inference", "user:profile", "user:sessions:claude_code"]

    def test_swap_returns_false_without_credentials(self, db, mock_credentials_path):
        """Test swap returns False when no credentials exist."""
        with patch("ralphx.core.auth.Database", return_value=db):
            with swap_credentials_for_loop() as has_creds:
                assert has_creds is False


class TestMigrationV6:
    """Test migration v6 adds OAuth metadata columns."""

    def test_new_columns_exist(self, db):
        """Test that migration v6 adds scopes, subscription_type, rate_limit_tier columns."""
        # The fixture already runs migrations, so columns should exist
        # Verify by storing credentials with new fields
        db.store_credentials(
            scope="global",
            access_token="test",
            expires_at=int(time.time()) + 3600,
            scopes='["user:inference"]',
            subscription_type="pro",
            rate_limit_tier="default_claude_pro",
        )

        creds = db.get_credentials()
        assert creds["scopes"] == '["user:inference"]'
        assert creds["subscription_type"] == "pro"
        assert creds["rate_limit_tier"] == "default_claude_pro"

    def test_update_credentials_with_new_fields(self, db):
        """Test update_credentials can update new fields."""
        # Create initial credentials
        cred_id = db.store_credentials(
            scope="global",
            access_token="old-token",
            expires_at=int(time.time()) + 3600,
        )

        # Update with new fields
        db.update_credentials(
            cred_id,
            access_token="new-token",
            scopes='["user:inference", "user:profile"]',
            subscription_type="max",
            rate_limit_tier="default_claude_max_20x",
        )

        creds = db.get_credentials()
        assert creds["access_token"] == "new-token"
        assert creds["scopes"] == '["user:inference", "user:profile"]'
        assert creds["subscription_type"] == "max"
        assert creds["rate_limit_tier"] == "default_claude_max_20x"


class TestCredentialFieldDocumentation:
    """Tests that verify documented behavior of credential fields.

    These tests serve as executable documentation for the credential format
    expected by Claude Code CLI.
    """

    def test_expires_at_in_milliseconds(self, db, mock_credentials_path):
        """Verify expiresAt is converted to milliseconds for Claude Code."""
        # Claude Code expects expiresAt in milliseconds, not seconds
        expires_at_seconds = int(time.time()) + 28800

        db.store_credentials(
            scope="global",
            access_token="test",
            expires_at=expires_at_seconds,
        )

        with patch("ralphx.core.auth.Database", return_value=db):
            with swap_credentials_for_loop() as has_creds:
                assert has_creds is True

                written_data = json.loads(mock_credentials_path.read_text())
                oauth = written_data["claudeAiOauth"]

                # Should be in milliseconds
                assert oauth["expiresAt"] == expires_at_seconds * 1000

    def test_subscription_type_values(self):
        """Document expected subscriptionType values.

        Known values:
        - "free": Free tier users
        - "pro": Pro subscription ($20/month)
        - "max": Max subscription ($100/month)

        TODO: Verify with Anthropic API documentation when available.
        """
        # This test documents expected values
        valid_types = ["free", "pro", "max"]
        assert "max" in valid_types  # Default used by RalphX

    def test_rate_limit_tier_values(self):
        """Document expected rateLimitTier values.

        Known values:
        - "default_claude_max_20x": Max subscription with 20x rate limit multiplier

        TODO: Verify with Anthropic API documentation when available.
        """
        # This test documents expected values
        assert "default_claude_max_20x".endswith("20x")  # 20x multiplier
