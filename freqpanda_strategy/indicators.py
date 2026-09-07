"""Indicator registry: maps an indicator `name` to a computation function and
the set of output column names it produces.

Built on the `ta` library (pure pandas/numpy, no compiled extensions), which
keeps the dependency footprint small and avoids the numpy-compatibility
issues that `pandas-ta` currently has on recent numpy releases.

Single-output indicators (RSI, EMA, SMA) expose one column named after the
indicator's `alias`. Multi-output indicators (MACD, Bollinger Bands) expose
`f"{alias}_{sub_name}"` columns (e.g. alias "macd1" -> "macd1_macd",
"macd1_signal", "macd1_hist") so conditions can reference each line
individually while still keeping every column tied to its declaring
indicator.

Adding a new indicator = write a `_compute` function + an `_outputs`
function + register both here. Nothing else in the package needs to change.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List, Set

import pandas as pd
import ta

Params = Dict[str, float]


@dataclass(frozen=True)
class IndicatorHandler:
    compute: Callable[[pd.DataFrame, str, Params], Dict[str, pd.Series]]
    outputs: Callable[[str], List[str]]
    param_names: Set[str]


def _rsi(df: pd.DataFrame, alias: str, params: Params) -> Dict[str, pd.Series]:
    period = int(params.get("period", 14))
    return {alias: ta.momentum.RSIIndicator(close=df["close"], window=period).rsi()}


def _ema(df: pd.DataFrame, alias: str, params: Params) -> Dict[str, pd.Series]:
    period = int(params.get("period", 20))
    return {alias: ta.trend.EMAIndicator(close=df["close"], window=period).ema_indicator()}


def _sma(df: pd.DataFrame, alias: str, params: Params) -> Dict[str, pd.Series]:
    period = int(params.get("period", 20))
    return {alias: ta.trend.SMAIndicator(close=df["close"], window=period).sma_indicator()}


def _single_output(alias: str) -> List[str]:
    return [alias]


def _macd(df: pd.DataFrame, alias: str, params: Params) -> Dict[str, pd.Series]:
    fast = int(params.get("fast_period", 12))
    slow = int(params.get("slow_period", 26))
    signal = int(params.get("signal_period", 9))
    macd_ind = ta.trend.MACD(
        close=df["close"], window_slow=slow, window_fast=fast, window_sign=signal
    )
    return {
        f"{alias}_macd": macd_ind.macd(),
        f"{alias}_signal": macd_ind.macd_signal(),
        f"{alias}_hist": macd_ind.macd_diff(),
    }


def _macd_outputs(alias: str) -> List[str]:
    return [f"{alias}_macd", f"{alias}_signal", f"{alias}_hist"]


def _bbands(df: pd.DataFrame, alias: str, params: Params) -> Dict[str, pd.Series]:
    period = int(params.get("period", 20))
    std_dev = float(params.get("std_dev", 2))
    bb = ta.volatility.BollingerBands(close=df["close"], window=period, window_dev=std_dev)
    return {
        f"{alias}_upper": bb.bollinger_hband(),
        f"{alias}_middle": bb.bollinger_mavg(),
        f"{alias}_lower": bb.bollinger_lband(),
    }


def _bbands_outputs(alias: str) -> List[str]:
    return [f"{alias}_upper", f"{alias}_middle", f"{alias}_lower"]


INDICATOR_REGISTRY: Dict[str, IndicatorHandler] = {
    "rsi": IndicatorHandler(compute=_rsi, outputs=_single_output, param_names={"period"}),
    "ema": IndicatorHandler(compute=_ema, outputs=_single_output, param_names={"period"}),
    "sma": IndicatorHandler(compute=_sma, outputs=_single_output, param_names={"period"}),
    "macd": IndicatorHandler(
        compute=_macd,
        outputs=_macd_outputs,
        param_names={"fast_period", "slow_period", "signal_period"},
    ),
    "bbands": IndicatorHandler(
        compute=_bbands, outputs=_bbands_outputs, param_names={"period", "std_dev"}
    ),
}
