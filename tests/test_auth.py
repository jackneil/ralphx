"""Tests for RalphX OAuth account management.

Tests the complete account flow:
- store_oauth_tokens() storing to accounts table
- swap_credentials_for_loop() writing correct JSON format to .credentials.json
- Account-based credential swapping for loop execution
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
    """Test store_oauth_tokens() with accounts table."""

    def test_store_tokens_with_all_fields(self, db):
        """Test storing tokens with all OAuth metadata fields."""
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
            result = store_oauth_tokens(tokens)

        assert result is not None
        assert result["email"] == "user@example.com"

        # Verify stored in accounts table
        account = db.get_account_by_email("user@example.com")
        assert account is not None
        assert account["access_token"] == "sk-ant-oat01-test-token"
        assert account["refresh_token"] == "sk-ant-ort01-test-refresh"
        assert account["email"] == "user@example.com"
        # Scopes are stored as JSON string
        assert json.loads(account["scopes"]) == ["user:inference", "user:profile", "user:sessions:claude_code"]
        assert account["subscription_type"] == "max"
        assert account["rate_limit_tier"] == "default_claude_max_20x"

    def test_store_tokens_requires_email(self, db):
        """Test that email is required for storing tokens."""
        tokens = {
            "access_token": "sk-ant-oat01-minimal",
            "expires_in": 28800,
        }

        with patch("ralphx.core.auth.Database", return_value=db):
            with pytest.raises(ValueError, match="Email is required"):
                store_oauth_tokens(tokens)

    def test_store_tokens_with_project_assignment(self, db):
        """Test storing tokens with project assignment."""
        # Create a project first
        db.create_project("test-proj", "test-proj", "Test Project", "/tmp/test")

        tokens = {
            "access_token": "sk-ant-oat01-test-token",
            "refresh_token": "sk-ant-ort01-test-refresh",
            "expires_in": 28800,
            "email": "user@example.com",
        }

        with patch("ralphx.core.auth.Database", return_value=db):
            result = store_oauth_tokens(tokens, project_id="test-proj")

        assert result is not None
        assert result["email"] == "user@example.com"

        # Verify account created
        account = db.get_account_by_email("user@example.com")
        assert account is not None

        # Verify project assignment created
        assignment = db.get_project_account_assignment("test-proj")
        assert assignment is not None
        assert assignment["account_id"] == account["id"]


class TestSwapCredentialsForLoop:
    """Test swap_credentials_for_loop() writes correct JSON format."""

    def test_swap_writes_all_six_fields(self, db, mock_credentials_path):
        """Test that swap_credentials_for_loop writes all 6 required fields."""
        # Create an account with all fields
        expires_at = int(time.time()) + 28800
        db.create_account(
            email="user@example.com",
            access_token="sk-ant-oat01-test",
            refresh_token="sk-ant-ort01-test",
            expires_at=expires_at,
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
        # Create account WITHOUT some optional fields
        expires_at = int(time.time()) + 28800
        db.create_account(
            email="user@example.com",
            access_token="sk-ant-oat01-old",
            refresh_token="sk-ant-ort01-old",
            expires_at=expires_at,
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

        # Create account with malformed scopes JSON
        db.create_account(
            email="user@example.com",
            access_token="sk-ant-oat01-test",
            refresh_token="sk-ant-ort01-test",
            expires_at=expires_at,
            scopes="not-valid-json{{{",
        )

        with patch("ralphx.core.auth.Database", return_value=db):
            with swap_credentials_for_loop() as has_creds:
                assert has_creds is True

                written_data = json.loads(mock_credentials_path.read_text())
                oauth = written_data.get("claudeAiOauth", {})

                # Should fall back to default scopes
                assert oauth["scopes"] == ["user:inference", "user:profile", "user:sessions:claude_code"]

    def test_swap_returns_false_without_accounts(self, db, mock_credentials_path):
        """Test swap returns False when no accounts exist."""
        with patch("ralphx.core.auth.Database", return_value=db):
            with swap_credentials_for_loop() as has_creds:
                assert has_creds is False

    def test_swap_uses_effective_account_for_project(self, db, mock_credentials_path):
        """Test swap uses effective account resolution for projects."""
        expires_at = int(time.time()) + 28800

        # Create default account
        db.create_account(
            email="default@example.com",
            access_token="default-token",
            refresh_token="default-refresh",
            expires_at=expires_at,
        )

        # Create project-specific account
        db.create_account(
            email="project@example.com",
            access_token="project-token",
            refresh_token="project-refresh",
            expires_at=expires_at,
        )

        # Create project and assign the project-specific account
        db.create_project("test-proj", "test-proj", "Test Project", "/tmp/test")
        project_account = db.get_account_by_email("project@example.com")
        db.assign_account_to_project("test-proj", project_account["id"])

        with patch("ralphx.core.auth.Database", return_value=db):
            with swap_credentials_for_loop(project_id="test-proj") as has_creds:
                assert has_creds is True

                written_data = json.loads(mock_credentials_path.read_text())
                oauth = written_data.get("claudeAiOauth", {})

                # Should use project-specific account
                assert oauth["accessToken"] == "project-token"


class TestAccountManagement:
    """Test account table operations."""

    def test_create_account(self, db):
        """Test creating a new account."""
        expires_at = int(time.time()) + 28800
        account = db.create_account(
            email="test@example.com",
            access_token="test-token",
            refresh_token="test-refresh",
            expires_at=expires_at,
            subscription_type="pro",
        )

        assert account is not None
        assert account["email"] == "test@example.com"
        assert account["subscription_type"] == "pro"
        assert account["is_default"]  # First account is default (SQLite stores as 1/0)

    def test_second_account_not_default(self, db):
        """Test that second account is not default."""
        expires_at = int(time.time()) + 28800

        # First account becomes default
        db.create_account(
            email="first@example.com",
            access_token="first-token",
            expires_at=expires_at,
        )

        # Second account should not be default
        second = db.create_account(
            email="second@example.com",
            access_token="second-token",
            expires_at=expires_at,
        )

        assert not second["is_default"]

    def test_set_default_account(self, db):
        """Test setting default account."""
        expires_at = int(time.time()) + 28800

        first = db.create_account(
            email="first@example.com",
            access_token="first-token",
            expires_at=expires_at,
        )

        second = db.create_account(
            email="second@example.com",
            access_token="second-token",
            expires_at=expires_at,
        )

        # Set second as default
        db.set_default_account(second["id"])

        # Re-fetch to get updated state
        first = db.get_account(first["id"])
        second = db.get_account(second["id"])

        assert not first["is_default"]
        assert second["is_default"]

    def test_get_effective_account_uses_assignment(self, db):
        """Test effective account uses project assignment."""
        expires_at = int(time.time()) + 28800

        # Default account
        db.create_account(
            email="default@example.com",
            access_token="default-token",
            expires_at=expires_at,
        )

        # Assigned account
        assigned = db.create_account(
            email="assigned@example.com",
            access_token="assigned-token",
            expires_at=expires_at,
        )

        # Create project and assign
        db.create_project("test-proj", "test-proj", "Test", "/tmp/test")
        db.assign_account_to_project("test-proj", assigned["id"])

        # Effective account should be assigned, not default
        effective = db.get_effective_account("test-proj")
        assert effective["email"] == "assigned@example.com"

    def test_get_effective_account_falls_back_to_default(self, db):
        """Test effective account falls back to default when no assignment."""
        expires_at = int(time.time()) + 28800

        db.create_account(
            email="default@example.com",
            access_token="default-token",
            expires_at=expires_at,
        )

        db.create_project("test-proj", "test-proj", "Test", "/tmp/test")

        # No assignment - should use default
        effective = db.get_effective_account("test-proj")
        assert effective["email"] == "default@example.com"


class TestCredentialFieldDocumentation:
    """Tests that verify documented behavior of credential fields.

    These tests serve as executable documentation for the credential format
    expected by Claude Code CLI.
    """

    def test_expires_at_in_milliseconds(self, db, mock_credentials_path):
        """Verify expiresAt is converted to milliseconds for Claude Code."""
        # Claude Code expects expiresAt in milliseconds, not seconds
        expires_at_seconds = int(time.time()) + 28800

        db.create_account(
            email="test@example.com",
            access_token="test",
            refresh_token="test-refresh",
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


class TestValidateAccountEndpoint:
    """Tests for POST /auth/accounts/{account_id}/validate endpoint.

    TODO: These test skeletons need implementation. They validate:
    - Token validation correctly calls validate_account_token
    - Validation status is persisted to database
    - Error handling for missing/deleted accounts
    - Concurrent validation requests are handled safely
    """

    def test_validate_account_success(self, db):
        """Test successful token validation updates status correctly.

        TODO: Verify expected behavior with user:
        - When validation succeeds, last_validated_at is set to current timestamp
        - validation_status is set to 'valid'
        - last_error is cleared to None
        - last_error_at is cleared to None
        """
        # TODO: Implement - mock validate_account_token to return (True, "")
        pass

    def test_validate_account_failure(self, db):
        """Test failed token validation updates status correctly.

        TODO: Verify expected behavior with user:
        - When validation fails, last_validated_at is still set
        - validation_status is set to 'invalid'
        - last_error contains the error message
        - last_error_at is set to current timestamp (ISO format)
        """
        # TODO: Implement - mock validate_account_token to return (False, "error msg")
        pass

    def test_validate_nonexistent_account_returns_404(self, db):
        """Test validating non-existent account returns 404.

        TODO: Verify expected behavior with user:
        - Request to validate account_id that doesn't exist returns 404
        """
        # TODO: Implement - call endpoint with invalid account_id
        pass

    def test_validate_deleted_account_returns_404(self, db):
        """Test validating soft-deleted account returns 404.

        TODO: Verify expected behavior with user:
        - Request to validate account_id that was soft-deleted returns 404
        """
        # TODO: Implement - create account, soft delete, try to validate
        pass

    def test_validate_concurrent_requests_handled_safely(self, db):
        """Test concurrent validation requests use locking correctly.

        TODO: Verify expected behavior with user:
        - Two concurrent validate requests don't cause duplicate API calls
        - File lock prevents race conditions on token refresh
        - Second request sees updated token from first and returns early
        """
        # TODO: Implement - mock validate_account_token and verify lock behavior
        pass

    def test_validate_updates_db_even_if_validation_succeeds(self, db):
        """Test that validation status is persisted even on success.

        TODO: Verify expected behavior with user:
        - Even when token is valid, we update the database with validation timestamp
        - This allows UI to show "last checked at" time
        """
        # TODO: Implement - mock success, verify DB was updated
        pass
