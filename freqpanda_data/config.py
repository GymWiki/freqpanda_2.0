"""Pipeline configuration: which exchange, which symbol/timeframe pairs, and
where to find the database. Kept as plain data (dataclasses + an optional
JSON loader) so adding a symbol/timeframe never requires touching code.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Union


@dataclass(frozen=True)
class SymbolTimeframe:
    symbol: str
    timeframe: str


@dataclass(frozen=True)
class PipelineConfig:
    exchange_id: str = "binance"
    pairs: List[SymbolTimeframe] = field(default_factory=list)
    # ISO 8601 timestamp, e.g. "2020-01-01T00:00:00Z". Only used the first
    # time a symbol/timeframe is fetched (no stored candles yet) -- after
    # that, updates are always incremental from the latest stored candle.
    backfill_since: str = "2020-01-01T00:00:00Z"
    # Falls back to the SUPABASE_DB_URL / DATABASE_URL env vars when unset,
    # see freqpanda_data.db.get_connection.
    database_url: Optional[str] = None

    @staticmethod
    def from_dict(raw: dict) -> "PipelineConfig":
        pairs = [SymbolTimeframe(**p) for p in raw.get("pairs", [])]
        kwargs = {k: v for k, v in raw.items() if k != "pairs"}
        return PipelineConfig(pairs=pairs, **kwargs)


def load_pipeline_config(path: Union[str, Path]) -> PipelineConfig:
    raw = json.loads(Path(path).read_text())
    return PipelineConfig.from_dict(raw)
