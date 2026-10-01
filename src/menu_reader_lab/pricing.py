"""Custo em dólar de uma leitura, a partir dos tokens e da tabela `pricing.json`."""

from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources
from typing import Any

from .readers.base import Usage


@lru_cache(maxsize=1)
def table() -> dict[str, Any]:
    text = resources.files("menu_reader_lab").joinpath("pricing.json").read_text(encoding="utf-8")
    return json.loads(text)


def find_model(model: str) -> dict[str, Any] | None:
    """Preço do modelo, aceitando nomes com data (`gpt-4.1-2025-04-14`)."""
    models = table()["models"]
    if model in models:
        return models[model]
    prefixes = [name for name in models if model.startswith(name)]
    return models[max(prefixes, key=len)] if prefixes else None


def cost_usd(model: str, usage: Usage) -> float | None:
    """Dólares gastos, ou None quando o modelo não está na tabela (não inventamos preço)."""
    price = find_model(model)
    if price is None:
        return None
    cached = min(usage.cached_input_tokens, usage.input_tokens)
    fresh = usage.input_tokens - cached
    cached_rate = price.get("cached_input", price["input"])
    total = fresh * price["input"] + cached * cached_rate + usage.output_tokens * price["output"]
    return total / 1_000_000
