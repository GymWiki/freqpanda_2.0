"""Phase 7: live/paper execution engine.

Reuses phase 1's strategy interpreter (`freqpanda_strategy`) unchanged for
indicator/condition evaluation -- see `live_interpreter.py`'s module
docstring for exactly what is and isn't reimplemented, and why.

Public entrypoints are processes, not imports: `python -m
freqpanda_execution.runner <bot_id>` runs one bot, and `python -m
freqpanda_execution.supervisor` runs the reconciliation loop that starts
and stops those per bots.desired_status. See README.md for the full
architecture and operational runbook.
"""
from .risk import CircuitBreakerTripped, OrderRejected, RiskLimits, RiskMiddleware, RiskViolation

__all__ = [
    "RiskLimits",
    "RiskMiddleware",
    "RiskViolation",
    "CircuitBreakerTripped",
    "OrderRejected",
]
