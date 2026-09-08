"""The FastAPI application: wires up the routers, a couple of exception
handlers, and an unauthenticated health check for docker/compose healthchecks.
"""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from freqpanda_strategy import StrategyValidationError

from .routers import backtests, bots, compare, optimizations, strategies

app = FastAPI(
    title="freqpanda API",
    description=(
        "Phase 5: strategy CRUD, backtest/optimization job queue, and results, "
        "wiring phases 1-4 together for a future webapp (phase 6)."
    ),
    version="0.1.0",
)


@app.exception_handler(StrategyValidationError)
def handle_strategy_validation_error(request: Request, exc: StrategyValidationError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": str(exc)})


@app.get("/health", tags=["health"])
def health() -> dict:
    return {"status": "ok"}


app.include_router(strategies.router, prefix="/api/v1")
app.include_router(backtests.router, prefix="/api/v1")
app.include_router(optimizations.router, prefix="/api/v1")
app.include_router(compare.router, prefix="/api/v1")
app.include_router(bots.router, prefix="/api/v1")
app.include_router(bots.credentials_router, prefix="/api/v1")
