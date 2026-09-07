import pytest
from pydantic import ValidationError

from freqpanda_strategy import ParamRange, StrategyDefinition


def _valid_definition_dict():
    return {
        "name": "test_strategy",
        "indicators": [
            {"name": "rsi", "alias": "rsi14", "params": {"period": 14}},
        ],
        "entry_conditions": {"type": "comparison", "left": "rsi14", "op": "lt", "right": 30},
        "exit_conditions": {"type": "comparison", "left": "rsi14", "op": "gt", "right": 70},
        "risk_management": {"stop_loss_pct": 0.02, "take_profit_pct": 0.05},
    }


def test_valid_definition_parses():
    definition = StrategyDefinition.model_validate(_valid_definition_dict())
    assert definition.name == "test_strategy"
    assert definition.risk_management.trailing_stop_pct is None


def test_param_range_resolves_to_default():
    pr = ParamRange(default=14, min=7, max=21, step=1)
    assert pr.default == 14


def test_param_range_default_out_of_bounds_rejected():
    with pytest.raises(ValidationError):
        ParamRange(default=100, min=7, max=21)


def test_param_range_min_greater_than_max_rejected():
    with pytest.raises(ValidationError):
        ParamRange(default=10, min=20, max=5)


def test_missing_risk_management_rejected():
    data = _valid_definition_dict()
    del data["risk_management"]
    with pytest.raises(ValidationError):
        StrategyDefinition.model_validate(data)


def test_missing_stop_loss_rejected():
    data = _valid_definition_dict()
    del data["risk_management"]["stop_loss_pct"]
    with pytest.raises(ValidationError):
        StrategyDefinition.model_validate(data)


def test_duplicate_indicator_alias_rejected():
    data = _valid_definition_dict()
    data["indicators"].append({"name": "ema", "alias": "rsi14", "params": {"period": 20}})
    with pytest.raises(ValidationError):
        StrategyDefinition.model_validate(data)


def test_invalid_alias_identifier_rejected():
    data = _valid_definition_dict()
    data["indicators"][0]["alias"] = "not a valid identifier!"
    with pytest.raises(ValidationError):
        StrategyDefinition.model_validate(data)


def test_logical_and_requires_at_least_two_conditions():
    data = _valid_definition_dict()
    data["entry_conditions"] = {
        "type": "logical",
        "op": "and",
        "conditions": [{"type": "comparison", "left": "rsi14", "op": "lt", "right": 30}],
    }
    with pytest.raises(ValidationError):
        StrategyDefinition.model_validate(data)


def test_logical_not_requires_exactly_one_condition():
    data = _valid_definition_dict()
    data["entry_conditions"] = {
        "type": "logical",
        "op": "not",
        "conditions": [
            {"type": "comparison", "left": "rsi14", "op": "lt", "right": 30},
            {"type": "comparison", "left": "rsi14", "op": "gt", "right": 70},
        ],
    }
    with pytest.raises(ValidationError):
        StrategyDefinition.model_validate(data)


def test_nested_logical_condition_parses():
    data = _valid_definition_dict()
    data["entry_conditions"] = {
        "type": "logical",
        "op": "and",
        "conditions": [
            {"type": "comparison", "left": "rsi14", "op": "lt", "right": 35},
            {
                "type": "logical",
                "op": "or",
                "conditions": [
                    {"type": "comparison", "left": "close", "op": "gt", "right": "rsi14"},
                    {"type": "comparison", "left": "volume", "op": "gt", "right": 0},
                ],
            },
        ],
    }
    definition = StrategyDefinition.model_validate(data)
    assert definition.entry_conditions.op == "and"
