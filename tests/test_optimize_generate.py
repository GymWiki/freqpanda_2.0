import random

import pytest

from freqpanda_optimize.generate import GenerationBounds, IndicatorBounds, generate_variants
from freqpanda_strategy import ParamRange, run_strategy
from freqpanda_strategy.validation import validate_definition


def _crossover_bounds():
    return GenerationBounds(
        crossover_indicators=[
            IndicatorBounds(name="ema", param_ranges={"period": (5, 50, 1)}),
            IndicatorBounds(name="sma", param_ranges={"period": (5, 50, 1)}),
        ],
    )


def _threshold_bounds():
    return GenerationBounds(
        threshold_indicators=[
            IndicatorBounds(name="rsi", param_ranges={"period": (7, 21, 1)}, threshold_range=(20.0, 80.0)),
        ],
    )


def test_generate_variants_crossover_only():
    variants = generate_variants(_crossover_bounds(), n=10, rng=random.Random(0))
    assert len(variants) == 10
    for v in variants:
        assert len(v.indicators) == 2
        assert v.entry_conditions.op == "crosses_above"
        assert v.exit_conditions.op == "crosses_below"
        for ind in v.indicators:
            assert isinstance(ind.params["period"], ParamRange)


def test_generate_variants_threshold_only():
    variants = generate_variants(_threshold_bounds(), n=10, rng=random.Random(0))
    for v in variants:
        assert len(v.indicators) == 1
        assert v.entry_conditions.op == "lt"
        assert v.exit_conditions.op == "gt"
        # entry threshold below exit threshold (oversold vs overbought band)
        assert v.entry_conditions.right < v.exit_conditions.right


def test_generate_variants_all_pass_schema_and_semantic_validation():
    bounds = GenerationBounds(
        crossover_indicators=_crossover_bounds().crossover_indicators,
        threshold_indicators=_threshold_bounds().threshold_indicators,
    )
    variants = generate_variants(bounds, n=20, rng=random.Random(42))
    assert len(variants) == 20
    for v in variants:
        validate_definition(v)  # raises on any invalid reference/indicator


def test_generate_variants_are_directly_backtestable(synthetic_ohlcv):
    bounds = _crossover_bounds()
    variants = generate_variants(bounds, n=3, rng=random.Random(1))
    for v in variants:
        trades = run_strategy(v, synthetic_ohlcv)
        assert isinstance(trades, list)


def test_generate_variants_deterministic_with_seeded_rng():
    a = generate_variants(_crossover_bounds(), n=5, rng=random.Random(123))
    b = generate_variants(_crossover_bounds(), n=5, rng=random.Random(123))
    assert [v.name for v in a] == [v.name for v in b]


def test_generate_variants_raises_without_any_indicator_bounds():
    with pytest.raises(ValueError):
        generate_variants(GenerationBounds(), n=5)


def test_threshold_indicator_missing_range_raises():
    bounds = GenerationBounds(
        threshold_indicators=[IndicatorBounds(name="rsi", param_ranges={"period": (7, 21, 1)})]
    )
    with pytest.raises(ValueError, match="threshold_range"):
        generate_variants(bounds, n=1, rng=random.Random(0))
