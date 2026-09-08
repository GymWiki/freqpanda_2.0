"""Request/response models for the API layer. `StrategyDefinition` itself
(phase 1) is used directly as the create/update request+response body for
strategies -- no separate DTO to keep in sync, and FastAPI validates
incoming JSON against it automatically.
"""
from __future__ import annotations

import datetime as dt
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, model_validator

from freqpanda_strategy import StrategyDefinition


class StrategyResponse(BaseModel):
    id: str
    name: str
    definition: StrategyDefinition
    created_at: dt.datetime
    updated_at: dt.datetime


class BacktestJobRequest(BaseModel):
    exchange: str = "binance"
    symbol: str
    timeframe: str
    start: Optional[dt.datetime] = None
    end: Optional[dt.datetime] = None
    initial_capital: float = 10_000.0
    fee_pct: float = Field(default=0.001, ge=0)
    slippage_pct: float = Field(default=0.0, ge=0)


class OptimizationJobRequest(BaseModel):
    exchange: str = "binance"
    symbol: str
    timeframe: str
    start: Optional[dt.datetime] = None
    end: Optional[dt.datetime] = None
    train_period_days: float = Field(gt=0)
    test_period_days: float = Field(gt=0)
    metric: str = "sharpe_ratio"
    n_trials: int = Field(default=50, gt=0)
    timeout_seconds: Optional[float] = Field(default=None, gt=0)
    initial_capital: float = 10_000.0
    fee_pct: float = Field(default=0.001, ge=0)
    slippage_pct: float = Field(default=0.0, ge=0)


class JobResponse(BaseModel):
    id: str
    job_type: str
    status: str
    strategy_id: str
    error: Optional[str] = None
    created_at: dt.datetime
    started_at: Optional[dt.datetime] = None
    finished_at: Optional[dt.datetime] = None


class BacktestDetailResponse(JobResponse):
    metrics: Optional[Dict[str, Any]] = None
    trades: Optional[List[Dict[str, Any]]] = None
    equity_curve: Optional[List[Dict[str, Any]]] = None


class OptimizationDetailResponse(JobResponse):
    metric: Optional[str] = None
    windows: Optional[List[Dict[str, Any]]] = None
    mean_in_sample_score: Optional[float] = None
    mean_out_of_sample_score: Optional[float] = None
    final_params: Optional[Dict[str, Any]] = None
    final_definition: Optional[Dict[str, Any]] = None


class BacktestSummary(BaseModel):
    job_id: str
    status: str
    created_at: dt.datetime
    started_at: Optional[dt.datetime] = None
    finished_at: Optional[dt.datetime] = None
    error: Optional[str] = None
    metrics: Optional[Dict[str, Any]] = None


class OptimizationSummary(BaseModel):
    job_id: str
    status: str
    created_at: dt.datetime
    started_at: Optional[dt.datetime] = None
    finished_at: Optional[dt.datetime] = None
    error: Optional[str] = None
    mean_in_sample_score: Optional[float] = None
    mean_out_of_sample_score: Optional[float] = None


class CompareRequest(BaseModel):
    job_ids: List[str] = Field(min_length=1)


class CompareRow(BaseModel):
    job_id: str
    strategy_id: str
    strategy_name: str
    metrics: Dict[str, Any]


# ---- phase 7: execution (bots, credentials) ----


class ExchangeCredentialCreateRequest(BaseModel):
    exchange_id: str
    label: str
    api_key: str
    api_secret: str
    password: Optional[str] = None


class ExchangeCredentialResponse(BaseModel):
    id: str
    exchange_id: str
    label: str
    created_at: dt.datetime


class BotCreateRequest(BaseModel):
    name: str
    strategy_id: str
    exchange_id: str
    symbol: str
    timeframe: str
    mode: Literal["paper", "live"]
    credential_id: Optional[str] = None
    initial_capital: float = Field(default=10_000.0, gt=0)
    fee_pct: float = Field(default=0.001, ge=0)
    slippage_pct: float = Field(default=0.0005, ge=0)
    max_drawdown_pct: float = Field(gt=0, lt=1)
    max_position_notional_pct: float = Field(default=1.0, gt=0)
    max_price_deviation_pct: float = Field(default=0.10, gt=0)
    # Requirement: switching a bot into live mode must be an explicit,
    # can't-happen-by-accident act, never an implicit side effect of some
    # other default (e.g. "mode" silently defaulting to "live", or a paper
    # config being live-ified by omitting a field). Setting `mode: "live"`
    # is deliberate already; this is a second, independent confirmation of
    # that same intent, so a client can't flip a bot live by, say, copying
    # a paper request and changing one field without noticing the stakes.
    confirm_live: bool = False

    @model_validator(mode="after")
    def _check_live_transition_is_explicit(self) -> "BotCreateRequest":
        if self.mode == "live":
            if self.credential_id is None:
                raise ValueError("mode='live' requires a credential_id")
            if not self.confirm_live:
                raise ValueError(
                    "mode='live' requires confirm_live=true -- this is a deliberate "
                    "safeguard against accidentally starting a bot with real money"
                )
        elif self.credential_id is not None:
            raise ValueError("mode='paper' must not have a credential_id")
        return self


class BotResponse(BaseModel):
    id: str
    name: str
    strategy_id: str
    exchange_id: str
    symbol: str
    timeframe: str
    mode: str
    credential_id: Optional[str] = None
    initial_capital: float
    fee_pct: float
    slippage_pct: float
    max_drawdown_pct: float
    max_position_notional_pct: float
    max_price_deviation_pct: float
    desired_status: str
    status: str
    status_message: Optional[str] = None
    created_at: dt.datetime
    updated_at: dt.datetime


class BotStateResponse(BaseModel):
    equity: float
    peak_equity: float
    position: Optional[Dict[str, Any]] = None
    last_price: Optional[float] = None
    last_heartbeat_at: Optional[dt.datetime] = None
    updated_at: dt.datetime


class BotTradeResponse(BaseModel):
    entry_time: dt.datetime
    exit_time: dt.datetime
    entry_price: float
    exit_price: float
    quantity: float
    exit_reason: str
    net_pnl_pct: float
    net_pnl_abs: float
    entry_order_id: Optional[str] = None
    exit_order_id: Optional[str] = None


class BotEventResponse(BaseModel):
    event_type: str
    message: str
    data: Optional[Dict[str, Any]] = None
    created_at: dt.datetime
