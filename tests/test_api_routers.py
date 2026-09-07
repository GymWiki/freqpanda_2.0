"""HTTP-layer tests: real FastAPI app + TestClient + real auth, but the DB
dependency is overridden (no real Postgres in this environment) and each
router's repository calls are patched so these tests exercise request
parsing, auth, validation, status codes and response shaping -- exactly
the code this phase adds -- without needing a live database.
"""
import datetime as dt
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from freqpanda_api.db import get_db
from freqpanda_api.main import app
from freqpanda_api.repositories.jobs import JobRecord
from freqpanda_api.repositories.strategies import StrategyRecord
from freqpanda_strategy import RiskManagement, StrategyDefinition

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


def _valid_definition_payload():
    return {
        "name": "ema_test",
        "indicators": [],
        "entry_conditions": {"type": "comparison", "left": "close", "op": "gt", "right": 100},
        "risk_management": {"stop_loss_pct": 0.02, "take_profit_pct": 0.05},
    }


def _strategy_record(definition):
    now = dt.datetime(2024, 1, 1, tzinfo=dt.timezone.utc)
    return StrategyRecord(
        id="strat_1", name=definition.name, definition=definition,
        created_by="owner-hash", created_at=now, updated_at=now,
    )


# ---- auth ----

def test_missing_api_key_returns_422(client):
    resp = client.get("/api/v1/strategies")
    assert resp.status_code == 422  # header required, none given


def test_invalid_api_key_returns_401(client):
    resp = client.get("/api/v1/strategies", headers={"X-API-Key": "wrong"})
    assert resp.status_code == 401


def test_health_needs_no_key(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


# ---- strategy CRUD ----

def test_create_strategy_returns_201():
    definition = StrategyDefinition.model_validate(_valid_definition_payload())
    with patch("freqpanda_api.routers.strategies.strategies_repo.create_strategy") as mock_create:
        mock_create.return_value = _strategy_record(definition)
        app.dependency_overrides[get_db] = _fake_db
        with TestClient(app) as c:
            resp = c.post("/api/v1/strategies", json=_valid_definition_payload(), headers=_auth_headers())
        app.dependency_overrides.clear()

    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "ema_test"
    assert body["id"] == "strat_1"


def test_create_strategy_with_unknown_indicator_returns_422():
    payload = _valid_definition_payload()
    payload["indicators"] = [{"name": "not_a_real_indicator", "alias": "x", "params": {}}]
    app.dependency_overrides[get_db] = _fake_db
    with TestClient(app) as c:
        resp = c.post("/api/v1/strategies", json=payload, headers=_auth_headers())
    app.dependency_overrides.clear()
    assert resp.status_code == 422
    assert "unknown indicator" in resp.json()["detail"].lower()


def test_create_strategy_structurally_invalid_returns_422(client):
    payload = _valid_definition_payload()
    del payload["risk_management"]
    resp = client.post("/api/v1/strategies", json=payload, headers=_auth_headers())
    assert resp.status_code == 422


def test_get_strategy_not_found_returns_404():
    with patch("freqpanda_api.routers.strategies.strategies_repo.get_strategy", return_value=None):
        app.dependency_overrides[get_db] = _fake_db
        with TestClient(app) as c:
            resp = c.get("/api/v1/strategies/strat_missing", headers=_auth_headers())
        app.dependency_overrides.clear()
    assert resp.status_code == 404


def test_list_strategies_returns_records():
    definition = StrategyDefinition.model_validate(_valid_definition_payload())
    with patch("freqpanda_api.routers.strategies.strategies_repo.list_strategies") as mock_list:
        mock_list.return_value = [_strategy_record(definition)]
        app.dependency_overrides[get_db] = _fake_db
        with TestClient(app) as c:
            resp = c.get("/api/v1/strategies", headers=_auth_headers())
        app.dependency_overrides.clear()
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_delete_strategy_not_found_returns_404():
    with patch("freqpanda_api.routers.strategies.strategies_repo.delete_strategy", return_value=False):
        app.dependency_overrides[get_db] = _fake_db
        with TestClient(app) as c:
            resp = c.delete("/api/v1/strategies/strat_1", headers=_auth_headers())
        app.dependency_overrides.clear()
    assert resp.status_code == 404


def test_delete_strategy_success_returns_204():
    with patch("freqpanda_api.routers.strategies.strategies_repo.delete_strategy", return_value=True):
        app.dependency_overrides[get_db] = _fake_db
        with TestClient(app) as c:
            resp = c.delete("/api/v1/strategies/strat_1", headers=_auth_headers())
        app.dependency_overrides.clear()
    assert resp.status_code == 204


# ---- backtest jobs ----

def _job_record(job_type="backtest"):
    now = dt.datetime(2024, 1, 1, tzinfo=dt.timezone.utc)
    return JobRecord(
        id="job_1", job_type=job_type, status="pending", strategy_id="strat_1",
        payload={}, error=None, created_by="owner-hash", created_at=now, started_at=None, finished_at=None,
    )


def test_create_backtest_enqueues_job_and_returns_202():
    definition = StrategyDefinition.model_validate(_valid_definition_payload())
    with patch("freqpanda_api.routers.backtests.strategies_repo.get_strategy", return_value=_strategy_record(definition)), \
         patch("freqpanda_api.routers.backtests.jobs_repo.create_job", return_value=_job_record()), \
         patch("freqpanda_api.routers.backtests.get_queue") as mock_get_queue:
        mock_queue = MagicMock()
        mock_get_queue.return_value = mock_queue
        app.dependency_overrides[get_db] = _fake_db
        with TestClient(app) as c:
            resp = c.post(
                "/api/v1/strategies/strat_1/backtests",
                json={"symbol": "BTC/USDT", "timeframe": "1h"},
                headers=_auth_headers(),
            )
        app.dependency_overrides.clear()

    assert resp.status_code == 202
    assert resp.json()["status"] == "pending"
    mock_queue.enqueue.assert_called_once()


def test_create_backtest_unknown_strategy_returns_404():
    with patch("freqpanda_api.routers.backtests.strategies_repo.get_strategy", return_value=None):
        app.dependency_overrides[get_db] = _fake_db
        with TestClient(app) as c:
            resp = c.post(
                "/api/v1/strategies/strat_missing/backtests",
                json={"symbol": "BTC/USDT", "timeframe": "1h"},
                headers=_auth_headers(),
            )
        app.dependency_overrides.clear()
    assert resp.status_code == 404


def test_get_backtest_detail_includes_result_when_completed():
    job = _job_record()
    with patch("freqpanda_api.routers.backtests.jobs_repo.get_job", return_value=job), \
         patch("freqpanda_api.routers.backtests.results_repo.get_backtest_result") as mock_result:
        mock_result.return_value = {
            "metrics": {"sharpe_ratio": 1.2}, "trades": [], "equity_curve": [],
        }
        app.dependency_overrides[get_db] = _fake_db
        with TestClient(app) as c:
            resp = c.get("/api/v1/backtests/job_1", headers=_auth_headers())
        app.dependency_overrides.clear()
    assert resp.status_code == 200
    assert resp.json()["metrics"]["sharpe_ratio"] == 1.2


def test_get_backtest_wrong_job_type_returns_404():
    job = _job_record(job_type="optimization")
    with patch("freqpanda_api.routers.backtests.jobs_repo.get_job", return_value=job):
        app.dependency_overrides[get_db] = _fake_db
        with TestClient(app) as c:
            resp = c.get("/api/v1/backtests/job_1", headers=_auth_headers())
        app.dependency_overrides.clear()
    assert resp.status_code == 404


# ---- optimization jobs ----

def test_create_optimization_enqueues_job_and_returns_202():
    definition = StrategyDefinition.model_validate(_valid_definition_payload())
    with patch("freqpanda_api.routers.optimizations.strategies_repo.get_strategy", return_value=_strategy_record(definition)), \
         patch("freqpanda_api.routers.optimizations.jobs_repo.create_job", return_value=_job_record(job_type="optimization")), \
         patch("freqpanda_api.routers.optimizations.get_queue") as mock_get_queue:
        mock_queue = MagicMock()
        mock_get_queue.return_value = mock_queue
        app.dependency_overrides[get_db] = _fake_db
        with TestClient(app) as c:
            resp = c.post(
                "/api/v1/strategies/strat_1/optimizations",
                json={
                    "symbol": "BTC/USDT", "timeframe": "1h",
                    "train_period_days": 60, "test_period_days": 20,
                },
                headers=_auth_headers(),
            )
        app.dependency_overrides.clear()

    assert resp.status_code == 202
    mock_queue.enqueue.assert_called_once()


def test_create_optimization_invalid_period_returns_422(client):
    resp = client.post(
        "/api/v1/strategies/strat_1/optimizations",
        json={"symbol": "BTC/USDT", "timeframe": "1h", "train_period_days": -1, "test_period_days": 20},
        headers=_auth_headers(),
    )
    assert resp.status_code == 422


# ---- compare ----

def test_compare_returns_metrics_for_each_job():
    job = _job_record()
    job = JobRecord(**{**job.__dict__, "status": "completed"})
    definition = StrategyDefinition.model_validate(_valid_definition_payload())
    with patch("freqpanda_api.routers.compare.jobs_repo.get_job", return_value=job), \
         patch("freqpanda_api.routers.compare.results_repo.get_backtest_result", return_value={"metrics": {"sharpe_ratio": 1.0}}), \
         patch("freqpanda_api.routers.compare.strategies_repo.get_strategy", return_value=_strategy_record(definition)):
        app.dependency_overrides[get_db] = _fake_db
        with TestClient(app) as c:
            resp = c.post("/api/v1/compare", json={"job_ids": ["job_1"]}, headers=_auth_headers())
        app.dependency_overrides.clear()
    assert resp.status_code == 200
    body = resp.json()
    assert body[0]["metrics"]["sharpe_ratio"] == 1.0
    assert body[0]["strategy_name"] == "ema_test"


def test_compare_incomplete_job_returns_409():
    job = _job_record()  # status="pending"
    with patch("freqpanda_api.routers.compare.jobs_repo.get_job", return_value=job):
        app.dependency_overrides[get_db] = _fake_db
        with TestClient(app) as c:
            resp = c.post("/api/v1/compare", json={"job_ids": ["job_1"]}, headers=_auth_headers())
        app.dependency_overrides.clear()
    assert resp.status_code == 409
