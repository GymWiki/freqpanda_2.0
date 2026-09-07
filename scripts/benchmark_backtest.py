#!/usr/bin/env python
"""Times a single backtest() run on ~1 year of 1h candles, and breaks the
time down into "generating trades" (freqpanda_strategy.run_strategy, the
per-candle interpreter loop) vs. "everything phase 3 adds" (equity curve +
metrics), so it's clear which part actually drives runtime.

Usage:
    python scripts/benchmark_backtest.py
"""
from __future__ import annotations

import statistics
import time

import numpy as np
import pandas as pd

from freqpanda_backtest import backtest
from freqpanda_strategy import load_strategy_definition, run_strategy

CANDLES_PER_YEAR_1H = 365 * 24
REPEATS = 10


def make_synthetic_ohlcv(n: int, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    t = np.arange(n)
    close = 100.0 + 15.0 * np.sin(2 * np.pi * t / 60) + rng.normal(0, 0.15, size=n)
    close = np.maximum(close, 1.0)
    open_ = np.roll(close, 1)
    open_[0] = close[0]
    high = np.maximum(open_, close) + rng.uniform(0.05, 0.3, size=n)
    low = np.minimum(open_, close) - rng.uniform(0.05, 0.3, size=n)
    volume = rng.uniform(100, 1000, size=n)
    index = pd.date_range("2024-01-01", periods=n, freq="1h")
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume}, index=index
    )


def time_it(fn, repeats=REPEATS):
    samples = []
    for _ in range(repeats):
        start = time.perf_counter()
        fn()
        samples.append(time.perf_counter() - start)
    return samples


def main():
    df = make_synthetic_ohlcv(CANDLES_PER_YEAR_1H)
    definition = load_strategy_definition("examples/ema_crossover.json")

    interpreter_samples = time_it(lambda: run_strategy(definition, df))
    full_backtest_samples = time_it(lambda: backtest(definition, df, fee_pct=0.001, slippage_pct=0.0005))

    trades = run_strategy(definition, df)

    print(f"Candles: {len(df)} (~1 year of 1h data)")
    print(f"Strategy: {definition.name}, trades generated: {len(trades)}")
    print(f"Repeats per measurement: {REPEATS}")
    print()
    print("run_strategy() only (phase-1 interpreter, per-candle loop):")
    print(f"  mean={statistics.mean(interpreter_samples)*1000:.2f} ms  "
          f"median={statistics.median(interpreter_samples)*1000:.2f} ms  "
          f"min={min(interpreter_samples)*1000:.2f} ms  max={max(interpreter_samples)*1000:.2f} ms")
    print()
    print("backtest() end-to-end (interpreter + equity curve + all metrics):")
    print(f"  mean={statistics.mean(full_backtest_samples)*1000:.2f} ms  "
          f"median={statistics.median(full_backtest_samples)*1000:.2f} ms  "
          f"min={min(full_backtest_samples)*1000:.2f} ms  max={max(full_backtest_samples)*1000:.2f} ms")
    print()
    metrics_only_ms = (statistics.mean(full_backtest_samples) - statistics.mean(interpreter_samples)) * 1000
    print(f"=> phase 3's own work (equity curve + metrics) adds ~{metrics_only_ms:.2f} ms on top of the interpreter")
    per_run = statistics.mean(full_backtest_samples)
    print(f"=> at {per_run*1000:.2f} ms/run, ~{int(1/per_run)} sequential runs/second, "
          f"~{int(3600/per_run):,} sequential runs/hour on one core")


if __name__ == "__main__":
    main()
