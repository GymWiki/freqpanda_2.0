"""Pydantic schema for strategy definitions.

A strategy definition is plain data (JSON/YAML) describing:
  - which indicators to compute, with their parameters
  - an entry-condition tree and an (optional) exit-condition tree, built out
    of comparisons ("rsi < 30", "ema_fast crosses_above ema_slow") combined
    with and/or/not
  - mandatory risk management (stop-loss / take-profit / optional trailing
    stop)

Every instance-configurable numeric parameter can be given either as a
plain number (fixed value) or as a `ParamRange` (a default plus min/max/step
bounds), so the same definition can later be fed to a hyperopt routine
without changing its shape.

This module has no knowledge of pandas, `ta`, or how conditions are
evaluated -- it only describes the *shape* of a valid strategy. Semantic
cross-checks that need the indicator registry (e.g. "does this alias exist")
live in `validation.py`.
"""
from __future__ import annotations

from typing import Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field, field_validator, model_validator

Number = Union[int, float]


class ParamRange(BaseModel):
    """A tunable parameter: a default value plus bounds for later optimization."""

    default: Number
    min: Number
    max: Number
    step: Optional[Number] = Field(default=None, gt=0)

    @model_validator(mode="after")
    def _check_bounds(self) -> "ParamRange":
        if self.min > self.max:
            raise ValueError(f"min ({self.min}) must be <= max ({self.max})")
        if not (self.min <= self.default <= self.max):
            raise ValueError(
                f"default ({self.default}) must lie within [{self.min}, {self.max}]"
            )
        return self


ParamValue = Union[Number, ParamRange]


def resolve_param(value: ParamValue) -> Number:
    """Return the concrete number to use for one interpreter run."""
    return value.default if isinstance(value, ParamRange) else value


class IndicatorConfig(BaseModel):
    """One technical indicator instance, identified by a unique alias.

    `name` selects the indicator implementation from the registry (e.g.
    "rsi", "ema", "macd", "bbands"). `alias` is how entry/exit conditions
    refer to this indicator's output column(s); it must be unique within a
    strategy definition.
    """

    name: str
    alias: str
    params: Dict[str, ParamValue] = Field(default_factory=dict)

    @field_validator("alias")
    @classmethod
    def _alias_is_identifier(cls, v: str) -> str:
        if not v.isidentifier():
            raise ValueError(
                f"alias '{v}' must be a valid identifier (letters, digits, "
                "underscore, not starting with a digit)"
            )
        return v


ComparisonOp = Literal["gt", "gte", "lt", "lte", "eq", "ne", "crosses_above", "crosses_below"]
LogicalOp = Literal["and", "or", "not"]

Operand = Union[Number, str]
"""Either a literal constant, or a string referencing an OHLCV column
("close", "high", ...) or an indicator output column (an indicator alias,
or `f"{alias}_{output}"` for multi-output indicators)."""


class Comparison(BaseModel):
    """A leaf condition: `left <op> right`."""

    type: Literal["comparison"] = "comparison"
    left: Operand
    op: ComparisonOp
    right: Operand


class Logical(BaseModel):
    """A boolean combination of nested condition nodes."""

    type: Literal["logical"] = "logical"
    op: LogicalOp
    conditions: List["ConditionNode"]

    @model_validator(mode="after")
    def _check_arity(self) -> "Logical":
        if self.op == "not" and len(self.conditions) != 1:
            raise ValueError("'not' requires exactly 1 nested condition")
        if self.op in ("and", "or") and len(self.conditions) < 2:
            raise ValueError(f"'{self.op}' requires at least 2 nested conditions")
        return self


ConditionNode = Union[Comparison, Logical]
Logical.model_rebuild()


class RiskManagement(BaseModel):
    """Mandatory risk parameters, kept separate from indicator-based conditions.

    Percentages are fractions, e.g. 0.02 == 2%. `trailing_stop_pct` is the
    only optional field: not every strategy needs a trailing stop, but
    stop-loss and take-profit are always required so no strategy definition
    can accidentally omit basic risk control.
    """

    stop_loss_pct: Number = Field(..., gt=0, lt=1)
    take_profit_pct: Number = Field(..., gt=0)
    trailing_stop_pct: Optional[Number] = Field(default=None, gt=0, lt=1)


class StrategyDefinition(BaseModel):
    """The full, strategy-agnostic definition of one trading strategy."""

    name: str
    description: Optional[str] = None
    timeframe: Optional[str] = None
    indicators: List[IndicatorConfig] = Field(default_factory=list)
    entry_conditions: ConditionNode = Field(..., discriminator="type")
    exit_conditions: Optional[ConditionNode] = Field(default=None, discriminator="type")
    risk_management: RiskManagement

    @model_validator(mode="after")
    def _check_unique_aliases(self) -> "StrategyDefinition":
        aliases = [ind.alias for ind in self.indicators]
        seen = set()
        dupes = set()
        for a in aliases:
            (dupes if a in seen else seen).add(a)
        if dupes:
            raise ValueError(f"duplicate indicator aliases: {sorted(dupes)}")
        return self
