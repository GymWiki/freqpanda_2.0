from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


def generate_synthetic_ohlcv(n: int = 500, seed: int = 42) -> pd.DataFrame:
    """A deterministic sine-wave price series with small noise.

    The oscillation is wide and slow enough to reliably produce both EMA
    crossovers and RSI excursions below 30 / above 70, which is what the
    example strategies' tests rely on.
    """
    rng = np.random.default_rng(seed)
    t = np.arange(n)
    base_price = 100.0
    amplitude = 15.0
    period = 60
    noise = rng.normal(0, 0.15, size=n)
    close = base_price + amplitude * np.sin(2 * np.pi * t / period) + noise
    close = np.maximum(close, 1.0)

    open_ = np.roll(close, 1)
    open_[0] = close[0]
    high = np.maximum(open_, close) + rng.uniform(0.05, 0.3, size=n)
    low = np.minimum(open_, close) - rng.uniform(0.05, 0.3, size=n)
    volume = rng.uniform(100, 1000, size=n)

    index = pd.date_range("2024-01-01", periods=n, freq="1h")
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
        index=index,
    )


@pytest.fixture
def synthetic_ohlcv() -> pd.DataFrame:
    return generate_synthetic_ohlcv()
