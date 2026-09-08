"""Exposes phase 7's execution engine to the webapp: bot CRUD, start/stop
(by flipping `bots.desired_status` -- the supervisor process does the rest,
see `freqpanda_execution/supervisor.py`), and read access to runtime state,
trades, and the audit-event log so the webapp can show live position, PnL,
and bot status (requirement 6 of the phase-7 brief).

This router is a thin HTTP wrapper around `freqpanda_execution.repository`
-- it owns no bot-lifecycle logic of its own, matching that module's own
"freqpanda_api depends on this, not vice versa" contract.
"""
from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status

from freqpanda_execution import repository as execution_repo

from .. import schemas
from ..auth import require_api_key
from ..db import get_db

router = APIRouter(prefix="/bots", tags=["bots"])
credentials_router = APIRouter(prefix="/exchange-credentials", tags=["exchange-credentials"])


# ---- exchange credentials ----


@credentials_router.post("", response_model=schemas.ExchangeCredentialResponse, status_code=status.HTTP_201_CREATED)
def create_exchange_credential(
    body: schemas.ExchangeCredentialCreateRequest,
    created_by: str = Depends(require_api_key),
    conn=Depends(get_db),
):
    summary = execution_repo.create_credential(
        conn, created_by, body.exchange_id, body.label, body.api_key, body.api_secret, body.password
    )
    return schemas.ExchangeCredentialResponse(
        id=summary.id, exchange_id=summary.exchange_id, label=summary.label, created_at=summary.created_at
    )


@credentials_router.get("", response_model=List[schemas.ExchangeCredentialResponse])
def list_exchange_credentials(created_by: str = Depends(require_api_key), conn=Depends(get_db)):
    return [
        schemas.ExchangeCredentialResponse(id=s.id, exchange_id=s.exchange_id, label=s.label, created_at=s.created_at)
        for s in execution_repo.list_credentials(conn, created_by)
    ]


@credentials_router.delete("/{credential_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_exchange_credential(credential_id: str, created_by: str = Depends(require_api_key), conn=Depends(get_db)):
    deleted = execution_repo.delete_credential(conn, credential_id, created_by)
    if not deleted:
        raise HTTPException(status_code=404, detail="Exchange credential not found")


# ---- bots ----


def _bot_to_response(record: execution_repo.BotRecord) -> schemas.BotResponse:
    return schemas.BotResponse(
        id=record.id, name=record.name, strategy_id=record.strategy_id, exchange_id=record.exchange_id,
        symbol=record.symbol, timeframe=record.timeframe, mode=record.mode, credential_id=record.credential_id,
        initial_capital=record.initial_capital, fee_pct=record.fee_pct, slippage_pct=record.slippage_pct,
        max_drawdown_pct=record.max_drawdown_pct, max_position_notional_pct=record.max_position_notional_pct,
        max_price_deviation_pct=record.max_price_deviation_pct, desired_status=record.desired_status,
        status=record.status, status_message=record.status_message,
        created_at=record.created_at, updated_at=record.updated_at,
    )


def _require_owned_credential(conn, credential_id: str, created_by: str) -> None:
    owned_ids = {c.id for c in execution_repo.list_credentials(conn, created_by)}
    if credential_id not in owned_ids:
        raise HTTPException(status_code=404, detail="Exchange credential not found")


@router.post("", response_model=schemas.BotResponse, status_code=status.HTTP_201_CREATED)
def create_bot(body: schemas.BotCreateRequest, created_by: str = Depends(require_api_key), conn=Depends(get_db)):
    """`body`'s own validation (see `schemas.BotCreateRequest`) already
    enforces that going live requires both a credential and an explicit
    `confirm_live=true`; this only additionally checks that the credential
    is one this caller actually owns, and always starts stopped -- creating
    a bot never itself starts it (see `start_bot` for that).
    """
    if body.credential_id is not None:
        _require_owned_credential(conn, body.credential_id, created_by)

    record = execution_repo.create_bot(
        conn, created_by,
        name=body.name, strategy_id=body.strategy_id, exchange_id=body.exchange_id, symbol=body.symbol,
        timeframe=body.timeframe, mode=body.mode, credential_id=body.credential_id,
        initial_capital=body.initial_capital, fee_pct=body.fee_pct, slippage_pct=body.slippage_pct,
        max_drawdown_pct=body.max_drawdown_pct, max_position_notional_pct=body.max_position_notional_pct,
        max_price_deviation_pct=body.max_price_deviation_pct,
    )
    return _bot_to_response(record)


@router.get("", response_model=List[schemas.BotResponse])
def list_bots(created_by: str = Depends(require_api_key), conn=Depends(get_db)):
    return [_bot_to_response(r) for r in execution_repo.list_bots(conn, created_by)]


@router.get("/{bot_id}", response_model=schemas.BotResponse)
def get_bot(bot_id: str, created_by: str = Depends(require_api_key), conn=Depends(get_db)):
    record = execution_repo.get_bot(conn, bot_id, created_by)
    if record is None:
        raise HTTPException(status_code=404, detail="Bot not found")
    return _bot_to_response(record)


@router.delete("/{bot_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_bot(bot_id: str, created_by: str = Depends(require_api_key), conn=Depends(get_db)):
    record = execution_repo.get_bot(conn, bot_id, created_by)
    if record is None:
        raise HTTPException(status_code=404, detail="Bot not found")
    if record.desired_status == "running":
        raise HTTPException(status_code=409, detail="Stop the bot before deleting it")
    execution_repo.delete_bot(conn, bot_id, created_by)


@router.post("/{bot_id}/start", response_model=schemas.BotResponse)
def start_bot(bot_id: str, created_by: str = Depends(require_api_key), conn=Depends(get_db)):
    """Flips `desired_status` to 'running' -- the supervisor process
    reconciles this into an actual running subprocess (or restarts one that
    crashed); it does not start anything itself. A live bot whose credential
    was deleted since it was created is refused here rather than left to
    fail inside the bot process.
    """
    record = execution_repo.get_bot(conn, bot_id, created_by)
    if record is None:
        raise HTTPException(status_code=404, detail="Bot not found")
    if record.mode == "live":
        _require_owned_credential(conn, record.credential_id, created_by)

    updated = execution_repo.set_desired_status(conn, bot_id, created_by, "running")
    return _bot_to_response(updated)


@router.post("/{bot_id}/stop", response_model=schemas.BotResponse)
def stop_bot(bot_id: str, created_by: str = Depends(require_api_key), conn=Depends(get_db)):
    updated = execution_repo.set_desired_status(conn, bot_id, created_by, "stopped")
    if updated is None:
        raise HTTPException(status_code=404, detail="Bot not found")
    return _bot_to_response(updated)


@router.get("/{bot_id}/state", response_model=schemas.BotStateResponse)
def get_bot_state(bot_id: str, created_by: str = Depends(require_api_key), conn=Depends(get_db)):
    state = execution_repo.get_state(conn, bot_id, created_by)
    if state is None:
        raise HTTPException(status_code=404, detail="Bot has no runtime state yet -- it has never been started")
    return schemas.BotStateResponse(
        equity=state.equity, peak_equity=state.peak_equity, position=state.position,
        last_price=state.last_price, last_heartbeat_at=state.last_heartbeat_at, updated_at=state.updated_at,
    )


@router.get("/{bot_id}/trades", response_model=List[schemas.BotTradeResponse])
def list_bot_trades(bot_id: str, limit: int = 200, created_by: str = Depends(require_api_key), conn=Depends(get_db)):
    return [schemas.BotTradeResponse(**t) for t in execution_repo.list_trades(conn, bot_id, created_by, limit=limit)]


@router.get("/{bot_id}/events", response_model=List[schemas.BotEventResponse])
def list_bot_events(bot_id: str, limit: int = 100, created_by: str = Depends(require_api_key), conn=Depends(get_db)):
    return [schemas.BotEventResponse(**e) for e in execution_repo.list_events(conn, bot_id, created_by, limit=limit)]
