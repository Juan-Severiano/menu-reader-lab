"""Contrato dos leitores: recebem arquivos (fotos ou PDF) e devolvem o cardápio no schema."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cached_input_tokens: int = 0


@dataclass
class ReadResult:
    menu: dict[str, Any] | None
    usage: Usage = field(default_factory=Usage)
    model: str = ""
    latency_s: float = 0.0
    error: str | None = None


class Reader(Protocol):
    name: str
    model: str
    paid: bool  # True quando cada leitura gasta dinheiro (exige teto de gasto)

    def read(self, files: list[Path]) -> ReadResult: ...
