"""Turns a strategy definition's `ParamRange` fields into an Optuna search
space, and turns one trial's suggested values back into a concrete
`StrategyDefinition` that `freqpanda_backtest.backtest()` can run.

Only indicator parameters can carry a `ParamRange` in the phase-1 schema
(`IndicatorConfig.params: Dict[str, ParamValue]`) -- `RiskManagement`'s
fields are plain numbers, not `ParamValue`. So phase 4 optimizes indicator
parameters only; extending risk parameters to be optimizable would be a
phase-1 schema change, not something bolted on here.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

import optuna

from freqpanda_strategy import IndicatorConfig, StrategyDefinition
from freqpanda_strategy.schema import Number, ParamRange


@dataclass(frozen=True)
class ParamSpec:
    """One tunable parameter, addressed as `f"{indicator_alias}.{param_name}"`
    (dot-joined, since aliases are validated identifiers and can't contain a
    dot themselves -- so the combined key is always unambiguous to split).
    """

    indicator_alias: str
    param_name: str
    param_range: ParamRange

    @property
    def key(self) -> str:
        return f"{self.indicator_alias}.{self.param_name}"


def build_search_space(definition: StrategyDefinition) -> List[ParamSpec]:
    """Every `ParamRange`-valued parameter across all of `definition`'s
    indicators. Empty if the definition has no tunable parameters (all
    params are fixed numbers) -- optimizing such a definition just re-runs
    the same backtest for every trial, which is a caller error to pass in,
    not something this module needs to guard against.
    """
    specs = []
    for indicator in definition.indicators:
        for name, value in indicator.params.items():
            if isinstance(value, ParamRange):
                specs.append(ParamSpec(indicator.alias, name, value))
    return specs


def _is_integer_range(pr: ParamRange) -> bool:
    values = [pr.min, pr.max, pr.default] + ([pr.step] if pr.step is not None else [])
    return all(isinstance(v, int) or float(v).is_integer() for v in values)


def suggest_params(trial: optuna.Trial, search_space: List[ParamSpec]) -> Dict[str, Number]:
    """Ask `trial` for one value per parameter in `search_space`. Ranges
    where min/max/step/default are all whole numbers use `suggest_int`
    (e.g. an indicator period); anything else uses `suggest_float`.
    """
    values: Dict[str, Number] = {}
    for spec in search_space:
        pr = spec.param_range
        if _is_integer_range(pr):
            step = int(pr.step) if pr.step is not None else 1
            values[spec.key] = trial.suggest_int(spec.key, int(pr.min), int(pr.max), step=step)
        else:
            values[spec.key] = trial.suggest_float(spec.key, float(pr.min), float(pr.max), step=pr.step)
    return values


def materialize_definition(definition: StrategyDefinition, values: Dict[str, Number]) -> StrategyDefinition:
    """Return a copy of `definition` with every `f"{alias}.{param}"` key in
    `values` overriding that indicator's parameter (replacing a `ParamRange`
    with a concrete number). Parameters not present in `values` are left
    untouched, including any `ParamRange` still on them -- `run_strategy`
    already falls back to `.default` for those.
    """
    new_indicators = []
    for indicator in definition.indicators:
        new_params = dict(indicator.params)
        for name in indicator.params:
            key = f"{indicator.alias}.{name}"
            if key in values:
                new_params[name] = values[key]
        new_indicators.append(IndicatorConfig(name=indicator.name, alias=indicator.alias, params=new_params))
    return definition.model_copy(update={"indicators": new_indicators})
