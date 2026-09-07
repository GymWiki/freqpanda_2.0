"""Request/response models for the API layer. `StrategyDefinition` itself
(phase 1) is used directly as the create/update request+response body for
strategies -- no separate DTO to keep in sync, and FastAPI validates
incoming JSON against it automatically.
"""
from __future__ import annotations

import datetime as dt
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

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
