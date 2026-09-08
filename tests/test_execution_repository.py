import datetime as dt
from unittest.mock import MagicMock

import pytest

from freqpanda_execution import repository
from freqpanda_strategy import RiskManagement, StrategyDefinition


def _mock_conn_with_cursor():
    conn = MagicMock()
    cursor = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cursor
    return conn, cursor


def _definition(name="ema_test"):
    return StrategyDefinition(
        name=name,
        indicators=[],
        entry_conditions={"type": "comparison", "left": "close", "op": "gt", "right": 100},
        risk_management=RiskManagement(stop_loss_pct=0.02, take_profit_pct=0.05),
    )


# ---- _json_safe ----


def test_json_safe_replaces_non_finite_floats_with_none():
    assert repository._json_safe(float("inf")) is None
    assert repository._json_safe(float("-inf")) is None
    assert repository._json_safe(float("nan")) is None
    assert repository._json_safe(1.5) == 1.5


def test_json_safe_recurses_into_dicts_and_lists():
    value = {"a": float("inf"), "b": [1.0, float("nan"), {"c": float("-inf")}]}
    result = repository._json_safe(value)
    assert result == {"a": None, "b": [1.0, None, {"c": None}]}


# ---- get_strategy_definition ----


def test_get_strategy_definition_returns_parsed_definition():
    conn, cursor = _mock_conn_with_cursor()
    definition = _definition()
    cursor.fetchone.return_value = (definition.model_dump(mode="json"),)

    result = repository.get_strategy_definition(conn, "strat_abc")

    assert result is not None
    assert result.name == "ema_test"
    sql, params = cursor.execute.call_args[0]
    assert "select definition from strategies" in sql
    assert params == ("strat_abc",)


def test_get_strategy_definition_returns_none_when_missing():
    conn, cursor = _mock_conn_with_cursor()
    cursor.fetchone.return_value = None

    assert repository.get_strategy_definition(conn, "strat_missing") is None


# ---- exchange credentials ----


def test_create_credential_encrypts_before_storing(monkeypatch):
    conn, cursor = _mock_conn_with_cursor()
    now = dt.datetime(2024, 1, 1, tzinfo=dt.timezone.utc)
    cursor.fetchone.return_value = ("cred_abc", "binance", "main", now)
    monkeypatch.setattr(repository, "encrypt_secret", lambda s: f"enc({s})")

    result = repository.create_credential(conn, "owner-hash", "binance", "main", "key123", "secret456")

    assert result.id == "cred_abc"
    conn.commit.assert_called_once()
    _, params = cursor.execute.call_args[0]
    assert "enc(key123)" in params
    assert "enc(secret456)" in params
    assert "key123" not in params  # plaintext never reaches the query params


def test_get_decrypted_credential_decrypts_all_fields(monkeypatch):
    conn, cursor = _mock_conn_with_cursor()
    cursor.fetchone.return_value = ("binance", "enc-key", "enc-secret", "enc-pass")
    monkeypatch.setattr(repository, "decrypt_secret", lambda s: s.replace("enc-", ""))

    result = repository.get_decrypted_credential(conn, "cred_abc")

    assert result.exchange_id == "binance"
    assert result.api_key == "key"
    assert result.api_secret == "secret"
    assert result.password == "pass"


def test_get_decrypted_credential_returns_none_when_missing():
    conn, cursor = _mock_conn_with_cursor()
    cursor.fetchone.return_value = None
    assert repository.get_decrypted_credential(conn, "cred_missing") is None


def test_delete_credential_returns_false_when_nothing_deleted():
    conn, cursor = _mock_conn_with_cursor()
    cursor.rowcount = 0
    assert repository.delete_credential(conn, "cred_x", "owner-hash") is False
    conn.commit.assert_called_once()


# ---- bots ----


_BOT_ROW = (
    "bot_1", "my bot", "strat_1", "binance", "BTC/USDT", "1h", "paper", None,
    1000.0, 0.001, 0.0005, 0.2, 1.0, 0.1, "stopped", "stopped", None, "owner-hash",
    dt.datetime(2024, 1, 1, tzinfo=dt.timezone.utc), dt.datetime(2024, 1, 1, tzinfo=dt.timezone.utc),
)


def test_create_bot_inserts_and_returns_record():
    conn, cursor = _mock_conn_with_cursor()
    cursor.fetchone.return_value = _BOT_ROW

    record = repository.create_bot(
        conn, "owner-hash",
        name="my bot", strategy_id="strat_1", exchange_id="binance", symbol="BTC/USDT",
        timeframe="1h", mode="paper", credential_id=None, initial_capital=1000.0,
        fee_pct=0.001, slippage_pct=0.0005, max_drawdown_pct=0.2,
        max_position_notional_pct=1.0, max_price_deviation_pct=0.1,
    )

    assert record.id == "bot_1"
    assert record.mode == "paper"
    conn.commit.assert_called_once()


def test_get_bot_scoped_by_created_by_returns_none_when_missing():
    conn, cursor = _mock_conn_with_cursor()
    cursor.fetchone.return_value = None
    assert repository.get_bot(conn, "bot_missing", "owner-hash") is None
    sql, params = cursor.execute.call_args[0]
    assert params == ("bot_missing", "owner-hash")


def test_get_bot_unscoped_does_not_filter_by_created_by():
    conn, cursor = _mock_conn_with_cursor()
    cursor.fetchone.return_value = _BOT_ROW
    result = repository.get_bot_unscoped(conn, "bot_1")
    assert result.id == "bot_1"
    sql, params = cursor.execute.call_args[0]
    assert params == ("bot_1",)
    assert "where id = %s and created_by" not in sql


def test_list_bots_by_desired_status_is_unscoped():
    conn, cursor = _mock_conn_with_cursor()
    cursor.fetchall.return_value = [_BOT_ROW]
    results = repository.list_bots_by_desired_status(conn, "running")
    assert len(results) == 1
    sql, params = cursor.execute.call_args[0]
    assert params == ("running",)


def test_set_desired_status_updates_and_returns_none_when_not_owned():
    conn, cursor = _mock_conn_with_cursor()
    cursor.fetchone.return_value = None
    result = repository.set_desired_status(conn, "bot_1", "owner-hash", "running")
    assert result is None
    conn.commit.assert_called_once()


def test_update_status_is_unscoped_and_sets_message():
    conn, cursor = _mock_conn_with_cursor()
    repository.update_status(conn, "bot_1", "error", "boom")
    sql, params = cursor.execute.call_args[0]
    assert params == ("error", "boom", "bot_1")
    conn.commit.assert_called_once()


def test_delete_bot_returns_true_when_a_row_was_deleted():
    conn, cursor = _mock_conn_with_cursor()
    cursor.rowcount = 1
    assert repository.delete_bot(conn, "bot_1", "owner-hash") is True


# ---- bot_state ----


def test_upsert_state_sanitizes_non_finite_values_in_position(monkeypatch):
    conn, cursor = _mock_conn_with_cursor()
    captured = {}

    def fake_json(value):
        captured["value"] = value
        return value

    monkeypatch.setattr(repository, "Json", fake_json)

    repository.upsert_state(
        conn, "bot_1", equity=1000.0, peak_equity=1100.0,
        position={"entry_price": float("nan")}, last_price=50.0,
    )

    assert captured["value"] == {"entry_price": None}
    conn.commit.assert_called_once()


def test_upsert_state_with_no_position_passes_none():
    conn, cursor = _mock_conn_with_cursor()
    repository.upsert_state(conn, "bot_1", equity=1000.0, peak_equity=1000.0, position=None, last_price=None)
    _, params = cursor.execute.call_args[0]
    assert params[3] is None  # position column


def test_get_state_joins_on_bots_for_owner_scoping():
    conn, cursor = _mock_conn_with_cursor()
    now = dt.datetime(2024, 1, 1, tzinfo=dt.timezone.utc)
    cursor.fetchone.return_value = ("bot_1", 1000.0, 1000.0, None, 50.0, now, now)

    state = repository.get_state(conn, "bot_1", "owner-hash")

    assert state.equity == 1000.0
    sql, params = cursor.execute.call_args[0]
    assert "join bots" in sql
    assert params == ("bot_1", "owner-hash")


def test_get_state_returns_none_when_missing():
    conn, cursor = _mock_conn_with_cursor()
    cursor.fetchone.return_value = None
    assert repository.get_state(conn, "bot_1", "owner-hash") is None


# ---- bot_trades / bot_events ----


def test_record_trade_inserts_and_returns_new_id():
    conn, cursor = _mock_conn_with_cursor()
    now = dt.datetime(2024, 1, 1, tzinfo=dt.timezone.utc)
    trade_id = repository.record_trade(
        conn, "bot_1", entry_time=now, exit_time=now, entry_price=100.0, exit_price=105.0,
        quantity=1.0, exit_reason="take_profit", net_pnl_pct=0.05, net_pnl_abs=5.0,
    )
    assert trade_id.startswith("bottrade")
    conn.commit.assert_called_once()


def test_list_trades_returns_dicts_scoped_by_created_by():
    conn, cursor = _mock_conn_with_cursor()
    now = dt.datetime(2024, 1, 1, tzinfo=dt.timezone.utc)
    cursor.fetchall.return_value = [(now, now, 100.0, 105.0, 1.0, "take_profit", 0.05, 5.0, None, None)]

    trades = repository.list_trades(conn, "bot_1", "owner-hash")

    assert trades[0]["exit_reason"] == "take_profit"
    assert trades[0]["net_pnl_abs"] == 5.0


def test_record_event_sanitizes_data_payload(monkeypatch):
    conn, cursor = _mock_conn_with_cursor()
    captured = {}
    monkeypatch.setattr(repository, "Json", lambda v: captured.setdefault("value", v))

    repository.record_event(conn, "bot_1", "entry", "entered", {"price": float("inf")})

    assert captured["value"] == {"price": None}


def test_list_events_returns_dicts_scoped_by_created_by():
    conn, cursor = _mock_conn_with_cursor()
    now = dt.datetime(2024, 1, 1, tzinfo=dt.timezone.utc)
    cursor.fetchall.return_value = [("entry", "entered", {"price": 100.0}, now)]

    events = repository.list_events(conn, "bot_1", "owner-hash")

    assert events[0]["event_type"] == "entry"
    assert events[0]["data"] == {"price": 100.0}
