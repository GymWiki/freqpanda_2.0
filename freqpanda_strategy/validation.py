"""Semantic validation that needs knowledge of the indicator registry, on
top of the structural checks Pydantic already performs on `StrategyDefinition`
(required fields, types, numeric bounds, condition arity, ...).

Checked here:
  - every indicator's `name` exists in the registry
  - every indicator's `params` keys are ones that indicator accepts
  - every column referenced in entry/exit conditions is either an OHLCV
    column or an output column of a declared indicator
"""
from __future__ import annotations

from typing import Iterator, List, Set

from .exceptions import StrategyValidationError
from .indicators import INDICATOR_REGISTRY
from .schema import Comparison, ConditionNode, Logical, StrategyDefinition

OHLCV_COLUMNS = {"open", "high", "low", "close", "volume"}


def _available_columns(definition: StrategyDefinition) -> Set[str]:
    columns = set(OHLCV_COLUMNS)
    for ind in definition.indicators:
        handler = INDICATOR_REGISTRY.get(ind.name)
        if handler is not None:
            columns.update(handler.outputs(ind.alias))
    return columns


def _operand_refs(node: ConditionNode) -> Iterator[str]:
    if isinstance(node, Comparison):
        for operand in (node.left, node.right):
            if isinstance(operand, str):
                yield operand
    elif isinstance(node, Logical):
        for child in node.conditions:
            yield from _operand_refs(child)


def validate_definition(definition: StrategyDefinition) -> None:
    """Raise `StrategyValidationError` with all problems found, or return None."""
    errors: List[str] = []

    for ind in definition.indicators:
        handler = INDICATOR_REGISTRY.get(ind.name)
        if handler is None:
            errors.append(
                f"indicator '{ind.alias}': unknown indicator name '{ind.name}'. "
                f"Available: {sorted(INDICATOR_REGISTRY)}"
            )
            continue
        unknown_params = set(ind.params) - handler.param_names
        if unknown_params:
            errors.append(
                f"indicator '{ind.alias}' ({ind.name}): unknown parameter(s) "
                f"{sorted(unknown_params)}. Allowed: {sorted(handler.param_names)}"
            )

    available = _available_columns(definition)
    condition_trees = [("entry_conditions", definition.entry_conditions)]
    if definition.exit_conditions is not None:
        condition_trees.append(("exit_conditions", definition.exit_conditions))

    for label, tree in condition_trees:
        for ref in _operand_refs(tree):
            if ref not in available:
                errors.append(
                    f"{label}: references unknown column '{ref}'. "
                    f"Available columns: {sorted(available)}"
                )

    if errors:
        message = "Invalid strategy definition '{}':\n- {}".format(
            definition.name, "\n- ".join(errors)
        )
        raise StrategyValidationError(message)
