"""Leitores sem custo, usados para validar o avaliador e a esteira.

`OracleReader` devolve o gabarito (nota perfeita). `NoisyReader` o degrada de um jeito conhecido:
se a nota dele não refletir o ruído aplicado, o avaliador está errado.
"""

from __future__ import annotations

import copy
import json
import random
import zlib
from pathlib import Path

from ..schema import truth_to_menu
from .base import ReadResult


def _truth_for(files: list[Path]) -> dict:
    return json.loads((files[0].parent / "truth.json").read_text(encoding="utf-8"))


class OracleReader:
    name = "oracle"
    model = "oracle"
    paid = False

    def __init__(self, inventory: bool = True) -> None:
        self.inventory = inventory

    def read(self, files: list[Path]) -> ReadResult:
        return ReadResult(menu=truth_to_menu(_truth_for(files), self.inventory), model=self.model)


class NoisyReader:
    """Degrada o gabarito: perde itens, erra preços, troca nomes e inventa itens."""

    name = "noisy"
    paid = False

    def __init__(
        self,
        drop: float = 0.1,
        price_error: float = 0.1,
        rename: float = 0.05,
        invent: float = 0.05,
        inventory: bool = True,
        seed: int = 0,
    ) -> None:
        self.drop, self.price_error, self.rename, self.invent = drop, price_error, rename, invent
        self.inventory = inventory
        self.seed = seed
        self.model = "noisy"

    def read(self, files: list[Path]) -> ReadResult:
        truth = copy.deepcopy(_truth_for(files))
        rng = random.Random(self.seed + zlib.crc32(str(files[0].parent.name).encode()))
        for cat in truth["categories"]:
            kept = []
            for product in cat["products"]:
                if rng.random() < self.drop:
                    continue
                if product["price"] is not None and rng.random() < self.price_error:
                    product["price"] = round(product["price"] + rng.choice([-1, 1, 10]), 2)
                if rng.random() < self.rename:
                    product["name"] = f"{product['name']} especial de outra casa"
                kept.append(product)
                if rng.random() < self.invent:
                    kept.append(
                        {
                            "name": f"Item inventado {rng.randint(100, 999)}",
                            "description": None,
                            "price": 9.9,
                        }
                    )
            cat["products"] = kept
        return ReadResult(menu=truth_to_menu(truth, self.inventory), model=self.model)
