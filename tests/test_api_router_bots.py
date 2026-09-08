import datetime as dt
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from freqpanda_api.db import get_db
from freqpanda_api.main import app
from freqpanda_execution.repository import BotRecord, BotState, CredentialSummary

API_KEY = "test-key"


def _fake_db():
    yield MagicMock()


@pytest.fixture(autouse=True)
def _configure_api_key(monkeypatch):
    monkeypatch.setenv("API_KEYS", API_KEY)


@pytest.fixture
def client():
    app.dependency_overrides[get_db] = _fake_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _auth_headers():
    return {"X-API-Key": API_KEY}


def _bot_record(**overrides):
    now = dt.datetime(2024, 1, 1, tzinfo=dt.timezone.utc)
    fields = dict(
        id="bot_1", name="my bot", strategy_id="strat_1", exchange_id="binance", symbol="BTC/USDT",
        timeframe="1h", mode="paper", credential_id=None, initial_capital=1000.0, fee_pct=0.001,
        slippage_pct=0.0005, max_drawdown_pct=0.2, max_position_notional_pct=1.0, max_price_deviation_pct=0.1,
        desired_status="stopped", status="stopped", status_message=None, created_by="owner-hash",
        created_at=now, updated_at=now,
    )
    fields.update(overrides)
    return BotRecord(**fields)


def _paper_bot_payload(**overrides):
    payload = dict(
        name="my bot", strategy_id="strat_1", exchange_id="binance", symbol="BTC/USDT", timeframe="1h",
        mode="paper", initial_capital=1000.0, max_drawdown_pct=0.2,
    )
    payload.update(overrides)
    return payload


# ---- bot creation ----


def test_create_paper_bot_returns_201(client):
    with patch("freqpanda_api.routers.bots.execution_repo.create_bot") as mock_create:
        mock_create.return_value = _bot_record()
        resp = client.post("/api/v1/bots", json=_paper_bot_payload(), headers=_auth_headers())

    assert resp.status_code == 201
    assert resp.json()["mode"] == "paper"


def test_create_live_bot_without_confirm_live_is_rejected(client):
    resp = client.post(
        "/api/v1/bots",
        json=_paper_bot_payload(mode="live", credential_id="cred_1"),
        headers=_auth_headers(),
    )
    assert resp.status_code == 422


def test_create_live_bot_without_credential_id_is_rejected(client):
    resp = client.post(
        "/api/v1/bots",
        json=_paper_bot_payload(mode="live", confirm_live=True),
        headers=_auth_headers(),
    )
    assert resp.status_code == 422


def test_create_paper_bot_with_a_credential_id_is_rejected(client):
    resp = client.post(
        "/api/v1/bots",
        json=_paper_bot_payload(mode="paper", credential_id="cred_1"),
        headers=_auth_headers(),
    )
    assert resp.status_code == 422


def test_create_live_bot_with_unowned_credential_returns_404(client):
    with patch("freqpanda_api.routers.bots.execution_repo.list_credentials") as mock_list:
        mock_list.return_value = []
        resp = client.post(
            "/api/v1/bots",
            json=_paper_bot_payload(mode="live", credential_id="cred_1", confirm_live=True),
            headers=_auth_headers(),
        )
    assert resp.status_code == 404


def test_create_live_bot_with_owned_credential_and_confirm_succeeds(client):
    with patch("freqpanda_api.routers.bots.execution_repo.list_credentials") as mock_list, \
         patch("freqpanda_api.routers.bots.execution_repo.create_bot") as mock_create:
        mock_list.return_value = [CredentialSummary(id="cred_1", exchange_id="binance", label="main", created_at=dt.datetime.now(dt.timezone.utc))]
        mock_create.return_value = _bot_record(mode="live", credential_id="cred_1")

        resp = client.post(
            "/api/v1/bots",
            json=_paper_bot_payload(mode="live", credential_id="cred_1", confirm_live=True),
            headers=_auth_headers(),
        )

    assert resp.status_code == 201
    assert resp.json()["mode"] == "live"
    assert resp.json()["credential_id"] == "cred_1"


# ---- listing / fetching ----


def test_list_bots_returns_records(client):
    with patch("freqpanda_api.routers.bots.execution_repo.list_bots") as mock_list:
        mock_list.return_value = [_bot_record()]
        resp = client.get("/api/v1/bots", headers=_auth_headers())
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_get_bot_returns_404_when_missing(client):
    with patch("freqpanda_api.routers.bots.execution_repo.get_bot") as mock_get:
        mock_get.return_value = None
        resp = client.get("/api/v1/bots/bot_missing", headers=_auth_headers())
    assert resp.status_code == 404


# ---- delete ----


def test_delete_running_bot_is_rejected_with_409(client):
    with patch("freqpanda_api.routers.bots.execution_repo.get_bot") as mock_get:
        mock_get.return_value = _bot_record(desired_status="running")
        resp = client.delete("/api/v1/bots/bot_1", headers=_auth_headers())
    assert resp.status_code == 409


def test_delete_stopped_bot_succeeds(client):
    with patch("freqpanda_api.routers.bots.execution_repo.get_bot") as mock_get, \
         patch("freqpanda_api.routers.bots.execution_repo.delete_bot") as mock_delete:
        mock_get.return_value = _bot_record(desired_status="stopped")
        resp = client.delete("/api/v1/bots/bot_1", headers=_auth_headers())
    assert resp.status_code == 204
    mock_delete.assert_called_once()


# ---- start / stop ----


def test_start_bot_returns_404_when_missing(client):
    with patch("freqpanda_api.routers.bots.execution_repo.get_bot") as mock_get:
        mock_get.return_value = None
        resp = client.post("/api/v1/bots/bot_missing/start", headers=_auth_headers())
    assert resp.status_code == 404


def test_start_live_bot_with_deleted_credential_returns_404(client):
    with patch("freqpanda_api.routers.bots.execution_repo.get_bot") as mock_get, \
         patch("freqpanda_api.routers.bots.execution_repo.list_credentials") as mock_list:
        mock_get.return_value = _bot_record(mode="live", credential_id="cred_gone")
        mock_list.return_value = []
        resp = client.post("/api/v1/bots/bot_1/start", headers=_auth_headers())
    assert resp.status_code == 404


def test_start_paper_bot_flips_desired_status(client):
    with patch("freqpanda_api.routers.bots.execution_repo.get_bot") as mock_get, \
         patch("freqpanda_api.routers.bots.execution_repo.set_desired_status") as mock_set:
        mock_get.return_value = _bot_record()
        mock_set.return_value = _bot_record(desired_status="running", status="starting")
        resp = client.post("/api/v1/bots/bot_1/start", headers=_auth_headers())
    assert resp.status_code == 200
    assert mock_set.call_args[0][1] == "bot_1"
    assert mock_set.call_args[0][3] == "running"
    assert resp.json()["desired_status"] == "running"


def test_stop_bot_returns_404_when_missing(client):
    with patch("freqpanda_api.routers.bots.execution_repo.set_desired_status") as mock_set:
        mock_set.return_value = None
        resp = client.post("/api/v1/bots/bot_missing/stop", headers=_auth_headers())
    assert resp.status_code == 404


def test_stop_bot_succeeds(client):
    with patch("freqpanda_api.routers.bots.execution_repo.set_desired_status") as mock_set:
        mock_set.return_value = _bot_record(desired_status="stopped")
        resp = client.post("/api/v1/bots/bot_1/stop", headers=_auth_headers())
    assert resp.status_code == 200
    assert resp.json()["desired_status"] == "stopped"


# ---- state / trades / events ----


def test_get_bot_state_returns_404_when_never_started(client):
    with patch("freqpanda_api.routers.bots.execution_repo.get_state") as mock_state:
        mock_state.return_value = None
        resp = client.get("/api/v1/bots/bot_1/state", headers=_auth_headers())
    assert resp.status_code == 404


def test_get_bot_state_returns_the_current_state(client):
    now = dt.datetime(2024, 1, 1, tzinfo=dt.timezone.utc)
    with patch("freqpanda_api.routers.bots.execution_repo.get_state") as mock_state:
        mock_state.return_value = BotState(
            bot_id="bot_1", equity=1050.0, peak_equity=1100.0, position=None,
            last_price=42.0, last_heartbeat_at=now, updated_at=now,
        )
        resp = client.get("/api/v1/bots/bot_1/state", headers=_auth_headers())
    assert resp.status_code == 200
    assert resp.json()["equity"] == 1050.0


def test_list_bot_trades_returns_the_trades(client):
    now = dt.datetime(2024, 1, 1, tzinfo=dt.timezone.utc)
    with patch("freqpanda_api.routers.bots.execution_repo.list_trades") as mock_trades:
        mock_trades.return_value = [{
            "entry_time": now, "exit_time": now, "entry_price": 100.0, "exit_price": 105.0,
            "quantity": 1.0, "exit_reason": "take_profit", "net_pnl_pct": 0.05, "net_pnl_abs": 5.0,
            "entry_order_id": None, "exit_order_id": None,
        }]
        resp = client.get("/api/v1/bots/bot_1/trades", headers=_auth_headers())
    assert resp.status_code == 200
    assert resp.json()[0]["exit_reason"] == "take_profit"


def test_list_bot_events_returns_the_events(client):
    now = dt.datetime(2024, 1, 1, tzinfo=dt.timezone.utc)
    with patch("freqpanda_api.routers.bots.execution_repo.list_events") as mock_events:
        mock_events.return_value = [{"event_type": "started", "message": "Bot started", "data": None, "created_at": now}]
        resp = client.get("/api/v1/bots/bot_1/events", headers=_auth_headers())
    assert resp.status_code == 200
    assert resp.json()[0]["event_type"] == "started"


# ---- exchange credentials ----


def test_create_exchange_credential_returns_201_without_leaking_secrets(client):
    now = dt.datetime(2024, 1, 1, tzinfo=dt.timezone.utc)
    with patch("freqpanda_api.routers.bots.execution_repo.create_credential") as mock_create:
        mock_create.return_value = CredentialSummary(id="cred_1", exchange_id="binance", label="main", created_at=now)
        resp = client.post(
            "/api/v1/exchange-credentials",
            json={"exchange_id": "binance", "label": "main", "api_key": "k", "api_secret": "s"},
            headers=_auth_headers(),
        )
    assert resp.status_code == 201
    body = resp.json()
    assert "api_key" not in body
    assert "api_secret" not in body


def test_delete_exchange_credential_returns_404_when_missing(client):
    with patch("freqpanda_api.routers.bots.execution_repo.delete_credential") as mock_delete:
        mock_delete.return_value = False
        resp = client.delete("/api/v1/exchange-credentials/cred_missing", headers=_auth_headers())
    assert resp.status_code == 404
