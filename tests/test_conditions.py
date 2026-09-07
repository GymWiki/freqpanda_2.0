import pandas as pd
import pytest

from freqpanda_strategy.conditions import evaluate_condition
from freqpanda_strategy.schema import Comparison, Logical


@pytest.fixture
def df():
    index = pd.date_range("2024-01-01", periods=5, freq="1h")
    return pd.DataFrame(
        {
            "close": [10.0, 12.0, 11.0, 9.0, 9.0],
            "fast": [1.0, 3.0, 3.0, 1.0, 1.0],
            "slow": [2.0, 2.0, 2.0, 2.0, 2.0],
        },
        index=index,
    )


def test_gt_comparison(df):
    node = Comparison(left="close", op="gt", right=10.0)
    result = evaluate_condition(node, df)
    assert list(result) == [False, True, True, False, False]


def test_eq_and_ne_with_constant(df):
    eq_node = Comparison(left="slow", op="eq", right=2.0)
    ne_node = Comparison(left="slow", op="ne", right=2.0)
    assert evaluate_condition(eq_node, df).all()
    assert not evaluate_condition(ne_node, df).any()


def test_crosses_above(df):
    node = Comparison(left="fast", op="crosses_above", right="slow")
    result = evaluate_condition(node, df)
    # fast: 1,3,3,1,1 vs slow=2 -> crosses above only at index 1
    assert list(result) == [False, True, False, False, False]


def test_crosses_below(df):
    node = Comparison(left="fast", op="crosses_below", right="slow")
    result = evaluate_condition(node, df)
    # fast drops from 3 (>2) to 1 (<2) at index 3
    assert list(result) == [False, False, False, True, False]


def test_logical_and(df):
    node = Logical(
        op="and",
        conditions=[
            Comparison(left="close", op="gt", right=9.5),
            Comparison(left="fast", op="gte", right=3.0),
        ],
    )
    result = evaluate_condition(node, df)
    assert list(result) == [False, True, True, False, False]


def test_logical_or(df):
    node = Logical(
        op="or",
        conditions=[
            Comparison(left="close", op="lt", right=9.5),
            Comparison(left="fast", op="gte", right=3.0),
        ],
    )
    result = evaluate_condition(node, df)
    assert list(result) == [False, True, True, True, True]


def test_logical_not(df):
    node = Logical(op="not", conditions=[Comparison(left="close", op="gt", right=10.0)])
    result = evaluate_condition(node, df)
    assert list(result) == [True, False, False, True, True]


def test_unknown_column_raises_key_error(df):
    node = Comparison(left="does_not_exist", op="gt", right=1.0)
    with pytest.raises(KeyError):
        evaluate_condition(node, df)
