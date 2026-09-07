"""Generates candidate strategy definitions at random, within caller-supplied
bounds -- a deliberately simple starting point (see the README for how to
grow this into something more directed).

Every generated variant follows one of two templates, chosen at random,
that mirror phase 1's own two example strategies:

  - **crossover**: two indicators of a moving-average-like type (their
    outputs are directly comparable, e.g. two EMAs, or an EMA and an SMA),
    entering on `a crosses_above b` and exiting on `a crosses_below b`.
  - **threshold**: one oscillator-like indicator (bounded, e.g. RSI),
    entering when it drops below a low threshold and exiting when it rises
    above a high threshold -- a mean-reversion shape.

Both templates keep every generated indicator's tunable parameters as
`ParamRange`s (not fixed numbers), so a generated variant can be evaluated
as-is (phase 1's interpreter resolves a `ParamRange` to its `.default`) or
handed straight to `optimize()` to tune further.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from freqpanda_strategy import IndicatorConfig, ParamRange, RiskManagement, StrategyDefinition
from freqpanda_strategy.schema import Number

ParamBounds = Dict[str, Tuple[Number, Number, Optional[Number]]]  # param -> (min, max, step)


@dataclass(frozen=True)
class IndicatorBounds:
    """Allowed range for one indicator type. `threshold_range` is only used
    by the threshold template (e.g. RSI's natural 0-100 range) and can be
    left unset for indicators only ever used in the crossover template.
    """

    name: str  # registry key, e.g. "ema", "rsi"
    param_ranges: ParamBounds
    threshold_range: Optional[Tuple[float, float]] = None


@dataclass(frozen=True)
class GenerationBounds:
    """What `generate_variants` is allowed to produce. At least one of
    `crossover_indicators` / `threshold_indicators` must be non-empty.
    """

    crossover_indicators: List[IndicatorBounds] = field(default_factory=list)
    threshold_indicators: List[IndicatorBounds] = field(default_factory=list)
    stop_loss_pct_range: Tuple[float, float] = (0.01, 0.05)
    take_profit_pct_range: Tuple[float, float] = (0.02, 0.10)
    trailing_stop_pct_range: Optional[Tuple[float, float]] = (0.01, 0.05)
    trailing_stop_probability: float = 0.3


def _ranged_params(param_ranges: ParamBounds) -> Dict[str, ParamRange]:
    params = {}
    for name, (lo, hi, step) in param_ranges.items():
        default = lo + (hi - lo) / 2
        if isinstance(lo, int) and isinstance(hi, int) and (step is None or isinstance(step, int)):
            default = round(default)
        params[name] = ParamRange(default=default, min=lo, max=hi, step=step)
    return params


def _random_risk_management(bounds: GenerationBounds, rng: random.Random) -> RiskManagement:
    stop_loss_pct = round(rng.uniform(*bounds.stop_loss_pct_range), 4)
    take_profit_pct = round(rng.uniform(*bounds.take_profit_pct_range), 4)
    trailing_stop_pct = None
    if bounds.trailing_stop_pct_range and rng.random() < bounds.trailing_stop_probability:
        trailing_stop_pct = round(rng.uniform(*bounds.trailing_stop_pct_range), 4)
    return RiskManagement(
        stop_loss_pct=stop_loss_pct, take_profit_pct=take_profit_pct, trailing_stop_pct=trailing_stop_pct
    )


def _generate_crossover_variant(bounds: GenerationBounds, rng: random.Random, index: int) -> StrategyDefinition:
    ind_a, ind_b = rng.choices(bounds.crossover_indicators, k=2)
    alias_a, alias_b = f"{ind_a.name}_a_{index}", f"{ind_b.name}_b_{index}"

    indicators = [
        IndicatorConfig(name=ind_a.name, alias=alias_a, params=_ranged_params(ind_a.param_ranges)),
        IndicatorConfig(name=ind_b.name, alias=alias_b, params=_ranged_params(ind_b.param_ranges)),
    ]
    return StrategyDefinition(
        name=f"generated_crossover_{index:03d}_{ind_a.name}_{ind_b.name}",
        description=f"Randomly generated crossover variant: {alias_a} vs {alias_b}.",
        indicators=indicators,
        entry_conditions={"type": "comparison", "left": alias_a, "op": "crosses_above", "right": alias_b},
        exit_conditions={"type": "comparison", "left": alias_a, "op": "crosses_below", "right": alias_b},
        risk_management=_random_risk_management(bounds, rng),
    )


def _generate_threshold_variant(bounds: GenerationBounds, rng: random.Random, index: int) -> StrategyDefinition:
    ind = rng.choice(bounds.threshold_indicators)
    if ind.threshold_range is None:
        raise ValueError(f"threshold_indicators entry '{ind.name}' needs a threshold_range")
    alias = f"{ind.name}_{index}"
    low, high = ind.threshold_range
    band = (high - low) * 0.4
    entry_threshold = round(rng.uniform(low, low + band), 2)
    exit_threshold = round(rng.uniform(high - band, high), 2)

    indicators = [IndicatorConfig(name=ind.name, alias=alias, params=_ranged_params(ind.param_ranges))]
    return StrategyDefinition(
        name=f"generated_threshold_{index:03d}_{ind.name}",
        description=f"Randomly generated mean-reversion variant on {alias}.",
        indicators=indicators,
        entry_conditions={"type": "comparison", "left": alias, "op": "lt", "right": entry_threshold},
        exit_conditions={"type": "comparison", "left": alias, "op": "gt", "right": exit_threshold},
        risk_management=_random_risk_management(bounds, rng),
    )


def generate_variants(
    bounds: GenerationBounds, n: int, rng: Optional[random.Random] = None
) -> List[StrategyDefinition]:
    """Generate `n` random strategy definitions within `bounds`. Each is
    independently either a crossover or a threshold variant (uniformly at
    random among whichever templates `bounds` makes available).
    """
    rng = rng or random.Random()
    templates = []
    if bounds.crossover_indicators:
        templates.append("crossover")
    if bounds.threshold_indicators:
        templates.append("threshold")
    if not templates:
        raise ValueError("GenerationBounds needs at least one of crossover_indicators/threshold_indicators")

    variants = []
    for i in range(n):
        template = rng.choice(templates)
        if template == "crossover":
            variants.append(_generate_crossover_variant(bounds, rng, i))
        else:
            variants.append(_generate_threshold_variant(bounds, rng, i))
    return variants
