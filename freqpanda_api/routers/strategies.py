from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status

from freqpanda_strategy import StrategyDefinition
from freqpanda_strategy.validation import validate_definition

from .. import schemas
from ..auth import require_api_key
from ..db import get_db
from ..repositories import strategies as strategies_repo
from ..serializers import strategy_to_response

router = APIRouter(prefix="/strategies", tags=["strategies"])


@router.post("", response_model=schemas.StrategyResponse, status_code=status.HTTP_201_CREATED)
def create_strategy(
    definition: StrategyDefinition,
    created_by: str = Depends(require_api_key),
    conn=Depends(get_db),
):
    """Validates `definition` against both the phase-1 Pydantic schema
    (handled automatically by FastAPI parsing the request body as
    `StrategyDefinition`) and the semantic layer (`validate_definition`,
    which needs the indicator registry to catch things like an unknown
    indicator name or a condition referencing a column nothing produces).
    """
    validate_definition(definition)
    record = strategies_repo.create_strategy(conn, definition, created_by)
    return strategy_to_response(record)


@router.get("", response_model=List[schemas.StrategyResponse])
def list_strategies(created_by: str = Depends(require_api_key), conn=Depends(get_db)):
    return [strategy_to_response(r) for r in strategies_repo.list_strategies(conn, created_by)]


@router.get("/{strategy_id}", response_model=schemas.StrategyResponse)
def get_strategy(strategy_id: str, created_by: str = Depends(require_api_key), conn=Depends(get_db)):
    record = strategies_repo.get_strategy(conn, strategy_id, created_by)
    if record is None:
        raise HTTPException(status_code=404, detail="Strategy not found")
    return strategy_to_response(record)


@router.put("/{strategy_id}", response_model=schemas.StrategyResponse)
def update_strategy(
    strategy_id: str,
    definition: StrategyDefinition,
    created_by: str = Depends(require_api_key),
    conn=Depends(get_db),
):
    validate_definition(definition)
    record = strategies_repo.update_strategy(conn, strategy_id, created_by, definition)
    if record is None:
        raise HTTPException(status_code=404, detail="Strategy not found")
    return strategy_to_response(record)


@router.delete("/{strategy_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_strategy(strategy_id: str, created_by: str = Depends(require_api_key), conn=Depends(get_db)):
    deleted = strategies_repo.delete_strategy(conn, strategy_id, created_by)
    if not deleted:
        raise HTTPException(status_code=404, detail="Strategy not found")
