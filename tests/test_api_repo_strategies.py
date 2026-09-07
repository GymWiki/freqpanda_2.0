import datetime as dt
from unittest.mock import MagicMock

import pytest

from freqpanda_api.repositories.strategies import (
    create_strategy,
    delete_strategy,
    get_strategy,
    list_strategies,
    update_strategy,
)
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


def _row(strategy_id, definition, created_by="owner-hash"):
    now = dt.datetime(2024, 1, 1, tzinfo=dt.timezone.utc)
    return (strategy_id, definition.name, definition.model_dump(mode="json"), created_by, now, now)


def test_create_strategy_inserts_and_returns_record():
    conn, cursor = _mock_conn_with_cursor()
    definition = _definition()
    cursor.fetchone.return_value = _row("strat_abc", definition)

    record = create_strategy(conn, definition, created_by="owner-hash")

    assert record.id == "strat_abc"
    assert record.name == "ema_test"
    assert record.definition.name == "ema_test"
    assert record.created_by == "owner-hash"
    conn.commit.assert_called_once()

    sql, params = cursor.execute.call_args[0]
    assert "insert into strategies" in sql
    assert params[1] == "ema_test"  # name column comes from definition.name


def test_get_strategy_scoped_by_created_by_returns_none_when_missing():
    conn, cursor = _mock_conn_with_cursor()
    cursor.fetchone.return_value = None
    result = get_strategy(conn, "strat_missing", "owner-hash")
    assert result is None
    sql, params = cursor.execute.call_args[0]
    assert params == ("strat_missing", "owner-hash")


def test_list_strategies_maps_all_rows():
    conn, cursor = _mock_conn_with_cursor()
    d1, d2 = _definition("a"), _definition("b")
    cursor.fetchall.return_value = [_row("strat_1", d1), _row("strat_2", d2)]

    records = list_strategies(conn, "owner-hash")

    assert [r.id for r in records] == ["strat_1", "strat_2"]
    assert [r.name for r in records] == ["a", "b"]


def test_update_strategy_returns_none_when_not_owned():
    conn, cursor = _mock_conn_with_cursor()
    cursor.fetchone.return_value = None
    result = update_strategy(conn, "strat_1", "owner-hash", _definition())
    assert result is None
    conn.commit.assert_called_once()


def test_update_strategy_returns_updated_record():
    conn, cursor = _mock_conn_with_cursor()
    updated_definition = _definition("renamed")
    cursor.fetchone.return_value = _row("strat_1", updated_definition)

    result = update_strategy(conn, "strat_1", "owner-hash", updated_definition)

    assert result.name == "renamed"


def test_delete_strategy_true_when_row_deleted():
    conn, cursor = _mock_conn_with_cursor()
    cursor.rowcount = 1
    assert delete_strategy(conn, "strat_1", "owner-hash") is True
    conn.commit.assert_called_once()


def test_delete_strategy_false_when_nothing_deleted():
    conn, cursor = _mock_conn_with_cursor()
    cursor.rowcount = 0
    assert delete_strategy(conn, "strat_1", "owner-hash") is False
