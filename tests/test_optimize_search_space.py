import optuna
import pytest

from freqpanda_optimize.search_space import build_search_space, materialize_definition, suggest_params
from freqpanda_strategy import IndicatorConfig, ParamRange, RiskManagement, StrategyDefinition

optuna.logging.set_verbosity(optuna.logging.WARNING)


def _definition():
    return StrategyDefinition(
        name="tunable",
        indicators=[
            IndicatorConfig(
                name="ema",
                alias="ema_fast",
                params={"period": ParamRange(default=12, min=5, max=20, step=1)},
            ),
            IndicatorConfig(
                name="ema",
                alias="ema_slow",
                params={"period": ParamRange(default=26, min=21, max=100, step=1)},
            ),
            IndicatorConfig(name="rsi", alias="rsi14", params={"period": 14}),  # fixed, not tunable
        ],
        entry_conditions={"type": "comparison", "left": "ema_fast", "op": "crosses_above", "right": "ema_slow"},
        exit_conditions={"type": "comparison", "left": "ema_fast", "op": "crosses_below", "right": "ema_slow"},
        risk_management=RiskManagement(stop_loss_pct=0.02, take_profit_pct=0.06),
    )


def test_build_search_space_finds_only_param_range_entries():
    space = build_search_space(_definition())
    keys = {spec.key for spec in space}
    assert keys == {"ema_fast.period", "ema_slow.period"}


def test_build_search_space_empty_for_definition_without_ranges():
    definition = StrategyDefinition(
        name="fixed",
        indicators=[IndicatorConfig(name="rsi", alias="rsi14", params={"period": 14})],
        entry_conditions={"type": "comparison", "left": "rsi14", "op": "lt", "right": 30},
        risk_management=RiskManagement(stop_loss_pct=0.02, take_profit_pct=0.05),
    )
    assert build_search_space(definition) == []


def _ask_trial():
    study = optuna.create_study(direction="maximize")
    return study.ask()


def test_suggest_params_uses_integer_suggestion_for_whole_number_ranges():
    space = build_search_space(_definition())
    trial = _ask_trial()
    values = suggest_params(trial, space)

    assert set(values) == {"ema_fast.period", "ema_slow.period"}
    assert 5 <= values["ema_fast.period"] <= 20
    assert isinstance(values["ema_fast.period"], int)
    assert 21 <= values["ema_slow.period"] <= 100


def test_suggest_params_uses_float_suggestion_for_fractional_ranges():
    definition = StrategyDefinition(
        name="fractional",
        indicators=[
            IndicatorConfig(
                name="bbands",
                alias="bb",
                params={"std_dev": ParamRange(default=2.0, min=1.5, max=3.0, step=0.1)},
            )
        ],
        entry_conditions={"type": "comparison", "left": "close", "op": "lte", "right": "bb_lower"},
        risk_management=RiskManagement(stop_loss_pct=0.02, take_profit_pct=0.05),
    )
    space = build_search_space(definition)
    trial = _ask_trial()
    values = suggest_params(trial, space)
    assert isinstance(values["bb.std_dev"], float)
    assert 1.5 <= values["bb.std_dev"] <= 3.0


def test_materialize_definition_overrides_only_given_keys():
    definition = _definition()
    materialized = materialize_definition(definition, {"ema_fast.period": 8})

    fast = next(i for i in materialized.indicators if i.alias == "ema_fast")
    slow = next(i for i in materialized.indicators if i.alias == "ema_slow")
    rsi = next(i for i in materialized.indicators if i.alias == "rsi14")

    assert fast.params["period"] == 8
    assert isinstance(slow.params["period"], ParamRange)  # untouched, still a range
    assert rsi.params["period"] == 14  # untouched fixed param

    # original definition is not mutated
    original_fast = next(i for i in definition.indicators if i.alias == "ema_fast")
    assert isinstance(original_fast.params["period"], ParamRange)


def test_materialize_definition_result_is_directly_usable_by_run_strategy(synthetic_ohlcv):
    from freqpanda_strategy import run_strategy

    definition = _definition()
    materialized = materialize_definition(definition, {"ema_fast.period": 8, "ema_slow.period": 30})
    trades = run_strategy(materialized, synthetic_ohlcv)
    assert isinstance(trades, list)
