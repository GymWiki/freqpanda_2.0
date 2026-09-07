#!/usr/bin/env python
"""Example run: optimize the phase-1 `examples/ema_crossover.json` strategy
with walk-forward validation, and print in-sample vs out-of-sample
performance per window.

Usage:
    python scripts/optimize_example.py
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from freqpanda_optimize import optimize, refit_on_full_history
from freqpanda_strategy import load_strategy_definition


def make_synthetic_ohlcv(n: int, seed: int = 11) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    t = np.arange(n)
    # A slow regime drift on top of the oscillation, so different
    # walk-forward windows see genuinely different market behavior --
    # otherwise every window would trivially agree with every other.
    drift = np.cumsum(rng.normal(0, 0.03, size=n))
    close = 100.0 + 15.0 * np.sin(2 * np.pi * t / 60) + drift + rng.normal(0, 0.2, size=n)
    close = np.maximum(close, 1.0)
    open_ = np.roll(close, 1)
    open_[0] = close[0]
    high = np.maximum(open_, close) + rng.uniform(0.05, 0.3, size=n)
    low = np.minimum(open_, close) - rng.uniform(0.05, 0.3, size=n)
    volume = rng.uniform(100, 1000, size=n)
    index = pd.date_range("2023-01-01", periods=n, freq="1h")
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume}, index=index
    )


def main():
    df = make_synthetic_ohlcv(24 * 200)  # ~200 days of hourly candles
    definition = load_strategy_definition("examples/ema_crossover.json")

    print(f"Optimizing '{definition.name}' over {len(df)} candles "
          f"({df.index[0]} .. {df.index[-1]})")
    print()

    result = optimize(
        definition,
        df,
        train_period=pd.Timedelta(days=60),
        test_period=pd.Timedelta(days=20),
        metric="sharpe_ratio",
        n_trials=25,
        backtest_kwargs={"fee_pct": 0.001, "slippage_pct": 0.0005},
    )

    print(result.summary().to_string(index=False))
    print()
    print(f"Mean in-sample Sharpe:     {result.mean_in_sample_score():.3f}")
    print(f"Mean out-of-sample Sharpe: {result.mean_out_of_sample_score():.3f}")
    degradation = result.mean_in_sample_score() - result.mean_out_of_sample_score()
    print(f"Degradation (in - out):    {degradation:.3f}")
    print()

    print("Per-window best parameters:")
    for w in result.windows:
        print(f"  {w.window.test_start.date()} .. {w.window.test_end.date()}: {w.best_params}")
    print()

    print("Refitting on the full dataset for a deployable parameter set...")
    final = refit_on_full_history(
        definition, df, metric="sharpe_ratio", n_trials=25,
        backtest_kwargs={"fee_pct": 0.001, "slippage_pct": 0.0005},
    )
    print(f"Final params: {final.best_params}")
    print(f"Full-history Sharpe: {final.in_sample_score:.3f} "
          f"(in-sample by construction -- see freqpanda_optimize/README.md)")


if __name__ == "__main__":
    main()
