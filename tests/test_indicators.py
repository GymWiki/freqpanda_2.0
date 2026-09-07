from freqpanda_strategy import IndicatorConfig, compute_indicators
from freqpanda_strategy.indicators import INDICATOR_REGISTRY


def test_registry_has_expected_indicators():
    assert {"rsi", "ema", "sma", "macd", "bbands"} <= set(INDICATOR_REGISTRY)


def test_rsi_single_output_column(synthetic_ohlcv):
    indicators = [IndicatorConfig(name="rsi", alias="rsi14", params={"period": 14})]
    result = compute_indicators(synthetic_ohlcv, indicators)
    assert "rsi14" in result.columns
    valid = result["rsi14"].dropna()
    assert (valid >= 0).all() and (valid <= 100).all()


def test_ema_tracks_close_direction(synthetic_ohlcv):
    indicators = [IndicatorConfig(name="ema", alias="ema20", params={"period": 20})]
    result = compute_indicators(synthetic_ohlcv, indicators)
    assert "ema20" in result.columns
    assert result["ema20"].dropna().shape[0] > 0


def test_macd_produces_three_columns(synthetic_ohlcv):
    indicators = [IndicatorConfig(name="macd", alias="macd1", params={})]
    result = compute_indicators(synthetic_ohlcv, indicators)
    for col in ("macd1_macd", "macd1_signal", "macd1_hist"):
        assert col in result.columns


def test_bbands_produces_ordered_bands(synthetic_ohlcv):
    indicators = [IndicatorConfig(name="bbands", alias="bb", params={"period": 20, "std_dev": 2})]
    result = compute_indicators(synthetic_ohlcv, indicators)
    subset = result.dropna(subset=["bb_upper", "bb_middle", "bb_lower"])
    assert (subset["bb_upper"] >= subset["bb_middle"]).all()
    assert (subset["bb_middle"] >= subset["bb_lower"]).all()


def test_compute_indicators_does_not_mutate_input(synthetic_ohlcv):
    original_columns = list(synthetic_ohlcv.columns)
    compute_indicators(synthetic_ohlcv, [IndicatorConfig(name="ema", alias="ema20", params={})])
    assert list(synthetic_ohlcv.columns) == original_columns
