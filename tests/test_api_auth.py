import pytest
from fastapi import HTTPException

from freqpanda_api.auth import require_api_key


def test_valid_key_returns_stable_hash(monkeypatch):
    monkeypatch.setenv("API_KEYS", "secret-one,secret-two")
    principal = require_api_key(x_api_key="secret-one")
    assert isinstance(principal, str)
    assert len(principal) == 64  # sha256 hex digest
    # same key -> same principal, every time
    assert require_api_key(x_api_key="secret-one") == principal


def test_different_keys_give_different_principals(monkeypatch):
    monkeypatch.setenv("API_KEYS", "secret-one,secret-two")
    assert require_api_key(x_api_key="secret-one") != require_api_key(x_api_key="secret-two")


def test_invalid_key_raises_401(monkeypatch):
    monkeypatch.setenv("API_KEYS", "secret-one")
    with pytest.raises(HTTPException) as exc_info:
        require_api_key(x_api_key="wrong")
    assert exc_info.value.status_code == 401


def test_no_keys_configured_raises_500(monkeypatch):
    monkeypatch.delenv("API_KEYS", raising=False)
    with pytest.raises(HTTPException) as exc_info:
        require_api_key(x_api_key="anything")
    assert exc_info.value.status_code == 500


def test_raw_key_never_appears_in_principal(monkeypatch):
    monkeypatch.setenv("API_KEYS", "super-secret-value")
    principal = require_api_key(x_api_key="super-secret-value")
    assert "super-secret-value" not in principal
