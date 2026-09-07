"""Evaluates a `ConditionNode` tree against a DataFrame of OHLCV + indicator
columns, producing one boolean pandas Series (aligned to the DataFrame's
index) that is True on candles where the whole condition tree holds.

This module knows nothing about specific strategies or indicators -- it only
understands the generic comparison/logical DSL from `schema.py` plus plain
column lookups, which is what keeps the interpreter strategy-agnostic.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .schema import Comparison, ConditionNode, Logical, Operand


def resolve_operand(operand: Operand, df: pd.DataFrame) -> pd.Series:
    if isinstance(operand, (int, float)):
        return pd.Series(float(operand), index=df.index)
    if operand not in df.columns:
        raise KeyError(
            f"Condition references unknown column '{operand}'. "
            f"Available columns: {sorted(df.columns)}"
        )
    return df[operand]


def _apply_op(op: str, left: pd.Series, right: pd.Series) -> pd.Series:
    if op == "gt":
        return left > right
    if op == "gte":
        return left >= right
    if op == "lt":
        return left < right
    if op == "lte":
        return left <= right
    if op == "eq":
        return pd.Series(np.isclose(left, right, equal_nan=False), index=left.index)
    if op == "ne":
        return pd.Series(~np.isclose(left, right, equal_nan=False), index=left.index)
    if op == "crosses_above":
        return (left.shift(1) <= right.shift(1)) & (left > right)
    if op == "crosses_below":
        return (left.shift(1) >= right.shift(1)) & (left < right)
    raise ValueError(f"Unsupported comparison operator '{op}'")


def evaluate_condition(node: ConditionNode, df: pd.DataFrame) -> pd.Series:
    """Recursively evaluate a condition tree, returning a bool Series.

    Rows where an operand is still NaN (e.g. during an indicator's warm-up
    period) naturally evaluate to False rather than raising, since pandas
    comparisons against NaN are False.
    """
    if isinstance(node, Comparison):
        left = resolve_operand(node.left, df)
        right = resolve_operand(node.right, df)
        result = _apply_op(node.op, left, right)
        return result.fillna(False).astype(bool)

    if isinstance(node, Logical):
        results = [evaluate_condition(child, df) for child in node.conditions]
        if node.op == "and":
            out = results[0]
            for r in results[1:]:
                out = out & r
            return out
        if node.op == "or":
            out = results[0]
            for r in results[1:]:
                out = out | r
            return out
        if node.op == "not":
            return ~results[0]

    raise TypeError(f"Unsupported condition node: {node!r}")
