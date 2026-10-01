"""Geração do conjunto sintético: cardápios com gabarito, reproduzíveis pela semente."""

from __future__ import annotations

import json
import random
import unicodedata
from pathlib import Path
from typing import Any

from .render import STYLE_BY_NAME, STYLES, render_menu
from .vocab import CATEGORIES, PIZZA_SIZES, RESTAURANTS


def _key(name: str) -> str:
    plain = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return "".join(ch for ch in plain.lower() if ch.isalnum())


def _price(rng: random.Random, low: float, high: float) -> float:
    base = rng.uniform(low, high)
    cents = rng.choice([0.0, 0.5, 0.9, 0.9, 0.99])
    return round(int(base) + cents, 2)


def make_truth(rng: random.Random) -> dict[str, Any]:
    """Sorteia categorias e itens. Nomes repetidos no mesmo cardápio são descartados."""
    names = rng.sample(list(CATEGORIES), k=rng.randint(3, 6))
    used: set[str] = set()
    categories = []
    for cat_name in names:
        (low, high), items = CATEGORIES[cat_name]
        picked = rng.sample(items, k=min(len(items), rng.randint(3, 8)))
        products = []
        for name, description in picked:
            variants = [(name, 0.0)]
            if cat_name == "Pizzas":
                variants = [(f"{name} - {size}", extra) for size, extra in PIZZA_SIZES]
            base = _price(rng, low, high)
            for variant, extra in variants:
                key = _key(variant)
                if key in used:
                    continue
                used.add(key)
                products.append(
                    {
                        "name": variant,
                        "description": description if rng.random() < 0.85 else None,
                        "price": round(base + extra, 2),
                    }
                )
        if products:
            categories.append({"name": cat_name, "products": products})
    return {"categories": categories}


def generate_dataset(out_dir: Path, n: int, seed: int) -> list[dict[str, Any]]:
    """Gera `n` cardápios, alternando os estilos, e grava `index.json`."""
    out_dir.mkdir(parents=True, exist_ok=True)
    entries = []
    for i in range(n):
        style = STYLES[i % len(STYLES)]
        rng = random.Random(seed * 100_003 + i)
        truth = make_truth(rng)
        restaurant = rng.choice(RESTAURANTS)
        menu_dir = out_dir / f"{i:03d}-{style.name}"
        menu_dir.mkdir(parents=True, exist_ok=True)
        files = render_menu(
            truth, STYLE_BY_NAME[style.name], restaurant, menu_dir, seed * 100_003 + i
        )
        (menu_dir / "truth.json").write_text(
            json.dumps(truth, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        entries.append(
            {
                "id": menu_dir.name,
                "style": style.name,
                "medium": style.medium,
                "restaurant": restaurant,
                "files": [str(p.relative_to(out_dir)) for p in files],
                "truth": str((menu_dir / "truth.json").relative_to(out_dir)),
                "items": sum(len(c["products"]) for c in truth["categories"]),
                "categories": len(truth["categories"]),
            }
        )
    index = {"seed": seed, "count": n, "styles": [s.name for s in STYLES], "menus": entries}
    (out_dir / "index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    return entries


def load_index(data_dir: Path) -> dict[str, Any]:
    return json.loads((data_dir / "index.json").read_text(encoding="utf-8"))
