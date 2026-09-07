"""CRUD for strategy definitions. Every read/write is scoped by
`created_by` (see `freqpanda_api.auth`) -- even in a single-tenant
deployment with one shared API key, this means the isolation a real
multi-user upgrade needs is already enforced, not bolted on later.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import List, Optional

from psycopg2.extras import Json

from freqpanda_strategy import StrategyDefinition

from ..ids import new_id

_COLUMNS = "id, name, definition, created_by, created_at, updated_at"


@dataclass(frozen=True)
class StrategyRecord:
    id: str
    name: str
    definition: StrategyDefinition
    created_by: str
    created_at: dt.datetime
    updated_at: dt.datetime


def _row_to_record(row) -> StrategyRecord:
    id_, name, definition_json, created_by, created_at, updated_at = row
    return StrategyRecord(
        id=id_,
        name=name,
        definition=StrategyDefinition.model_validate(definition_json),
        created_by=created_by,
        created_at=created_at,
        updated_at=updated_at,
    )


def create_strategy(conn, definition: StrategyDefinition, created_by: str) -> StrategyRecord:
    strategy_id = new_id("strat")
    with conn.cursor() as cur:
        cur.execute(
            f"""
            insert into strategies (id, name, definition, created_by)
            values (%s, %s, %s, %s)
            returning {_COLUMNS}
            """,
            (strategy_id, definition.name, Json(definition.model_dump(mode="json")), created_by),
        )
        row = cur.fetchone()
    conn.commit()
    return _row_to_record(row)


def get_strategy(conn, strategy_id: str, created_by: str) -> Optional[StrategyRecord]:
    with conn.cursor() as cur:
        cur.execute(
            f"select {_COLUMNS} from strategies where id = %s and created_by = %s",
            (strategy_id, created_by),
        )
        row = cur.fetchone()
    return _row_to_record(row) if row else None


def list_strategies(conn, created_by: str) -> List[StrategyRecord]:
    with conn.cursor() as cur:
        cur.execute(
            f"select {_COLUMNS} from strategies where created_by = %s order by created_at desc",
            (created_by,),
        )
        rows = cur.fetchall()
    return [_row_to_record(row) for row in rows]


def update_strategy(
    conn, strategy_id: str, created_by: str, definition: StrategyDefinition
) -> Optional[StrategyRecord]:
    with conn.cursor() as cur:
        cur.execute(
            f"""
            update strategies
            set name = %s, definition = %s, updated_at = now()
            where id = %s and created_by = %s
            returning {_COLUMNS}
            """,
            (definition.name, Json(definition.model_dump(mode="json")), strategy_id, created_by),
        )
        row = cur.fetchone()
    conn.commit()
    return _row_to_record(row) if row else None


def delete_strategy(conn, strategy_id: str, created_by: str) -> bool:
    with conn.cursor() as cur:
        cur.execute("delete from strategies where id = %s and created_by = %s", (strategy_id, created_by))
        deleted = cur.rowcount > 0
    conn.commit()
    return deleted
