"""Load a `StrategyDefinition` from a JSON or YAML file on disk."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Union

import yaml

from .schema import StrategyDefinition


def load_strategy_definition(path: Union[str, Path]) -> StrategyDefinition:
    path = Path(path)
    text = path.read_text()
    if path.suffix.lower() in (".yaml", ".yml"):
        raw = yaml.safe_load(text)
    else:
        raw = json.loads(text)
    return StrategyDefinition.model_validate(raw)
