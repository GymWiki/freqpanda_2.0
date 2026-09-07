#!/usr/bin/env python
"""Compares running many strategy variants sequentially vs. via
run_backtests_parallel(), on the same 1-year-of-1h synthetic dataset used
by benchmark_backtest.py.

Usage:
    python scripts/benchmark_parallel.py
"""
from __future__ import annotations

import time

from freqpanda_backtest import backtest, run_backtests_parallel
from freqpanda_strategy import RiskManagement, StrategyDefinition

from benchmark_backtest import make_synthetic_ohlcv, CANDLES_PER_YEAR_1H

N_VARIANTS = 40


def make_variants(n):
    variants = []
    for i in range(n):
        period = 5 + i  # vary the EMA period so each variant does real (different) work
        variants.append(
            StrategyDefinition(
                name=f"ema_fast_{period}",
                indicators=[
                    {"name": "ema", "alias": "ema_fast", "params": {"period": period}},
                    {"name": "ema", "alias": "ema_slow", "params": {"period": period + 20}},
                ],
                entry_conditions={
                    "type": "comparison", "left": "ema_fast", "op": "crosses_above", "right": "ema_slow"
                },
                exit_conditions={
                    "type": "comparison", "left": "ema_fast", "op": "crosses_below", "right": "ema_slow"
                },
                risk_management=RiskManagement(stop_loss_pct=0.02, take_profit_pct=0.06),
            )
        )
    return variants


def main():
    df = make_synthetic_ohlcv(CANDLES_PER_YEAR_1H)
    variants = make_variants(N_VARIANTS)

    start = time.perf_counter()
    for v in variants:
        backtest(v, df, fee_pct=0.001)
    sequential_time = time.perf_counter() - start

    start = time.perf_counter()
    run_backtests_parallel(variants, df, fee_pct=0.001)
    parallel_time = time.perf_counter() - start

    print(f"{N_VARIANTS} variants, {len(df)} candles each")
    print(f"sequential: {sequential_time:.2f}s ({sequential_time/N_VARIANTS*1000:.1f} ms/variant)")
    print(f"parallel:   {parallel_time:.2f}s ({parallel_time/N_VARIANTS*1000:.1f} ms/variant)")
    print(f"speedup:    {sequential_time/parallel_time:.2f}x")


if __name__ == "__main__":
    main()
