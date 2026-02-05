import os

import pytest

from pulsefm_auth.session import issue_session_token, verify_session_token


def test_issue_and_verify_session_token(monkeypatch):
    monkeypatch.setenv("SESSION_JWT_SECRET", "test-secret")
    token, meta = issue_session_token()
    claims = verify_session_token(token)
    assert claims["sid"] == meta["session_id"]
    assert "exp" in claims


def test_missing_secret_raises(monkeypatch):
    monkeypatch.delenv("SESSION_JWT_SECRET", raising=False)
    with pytest.raises(ValueError):
        issue_session_token()
