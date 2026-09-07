import pytest

from freqpanda_strategy import StrategyDefinition, StrategyValidationError
from freqpanda_strategy.validation import validate_definition


def _base_dict():
    return {
        "name": "validation_test",
        "indicators": [{"name": "rsi", "alias": "rsi14", "params": {"period": 14}}],
        "entry_conditions": {"type": "comparison", "left": "rsi14", "op": "lt", "right": 30},
        "exit_conditions": None,
        "risk_management": {"stop_loss_pct": 0.02, "take_profit_pct": 0.05},
    }


def test_valid_definition_passes_validation():
    definition = StrategyDefinition.model_validate(_base_dict())
    validate_definition(definition)  # should not raise


def test_unknown_indicator_name_raises():
    data = _base_dict()
    data["indicators"][0]["name"] = "not_a_real_indicator"
    definition = StrategyDefinition.model_validate(data)
    with pytest.raises(StrategyValidationError, match="unknown indicator name"):
        validate_definition(definition)


def test_unknown_indicator_param_raises():
    data = _base_dict()
    data["indicators"][0]["params"] = {"not_a_param": 5}
    definition = StrategyDefinition.model_validate(data)
    with pytest.raises(StrategyValidationError, match="unknown parameter"):
        validate_definition(definition)


def test_condition_referencing_unknown_column_raises():
    data = _base_dict()
    data["entry_conditions"] = {
        "type": "comparison",
        "left": "does_not_exist",
        "op": "lt",
        "right": 30,
    }
    definition = StrategyDefinition.model_validate(data)
    with pytest.raises(StrategyValidationError, match="unknown column"):
        validate_definition(definition)


def test_condition_can_reference_ohlcv_columns_without_indicator():
    data = _base_dict()
    data["entry_conditions"] = {"type": "comparison", "left": "close", "op": "gt", "right": 0}
    definition = StrategyDefinition.model_validate(data)
    validate_definition(definition)  # should not raise


def test_multi_output_indicator_columns_are_recognised():
    data = _base_dict()
    data["indicators"].append({"name": "macd", "alias": "macd1", "params": {}})
    data["exit_conditions"] = {
        "type": "comparison",
        "left": "macd1_macd",
        "op": "crosses_below",
        "right": "macd1_signal",
    }
    definition = StrategyDefinition.model_validate(data)
    validate_definition(definition)  # should not raise
