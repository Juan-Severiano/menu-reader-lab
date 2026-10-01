"""Avaliação de um cardápio lido contra o gabarito.

Os itens são casados pelo nome (sem acento, caixa ou pontuação, com tolerância a erro de
leitura). Item lido sem par no gabarito conta como **inventado ou duplicado** (falso positivo).
Item do gabarito sem par conta como **perdido** (falso negativo).
"""

from __future__ import annotations

import unicodedata
from dataclasses import asdict, dataclass, field
from typing import Any

from rapidfuzz import fuzz

from .schema import validate

NAME_THRESHOLD = 88
CATEGORY_THRESHOLD = 80
PRICE_TOLERANCE = 0.005


def norm(text: Any) -> str:
    plain = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode().lower()
    return " ".join("".join(ch if ch.isalnum() else " " for ch in plain).split())


def to_price(value: Any) -> float | None:
    """Aceita número ou texto ("12,90"). Qualquer outra coisa vira None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.replace("R$", "").strip()
        if "," in text:
            text = text.replace(".", "").replace(",", ".")
        try:
            return float(text)
        except ValueError:
            return None
    return None


@dataclass
class Item:
    category: str
    name: str
    price: float | None


def flatten(menu: Any) -> list[Item]:
    """Lista os produtos de um cardápio, ignorando o que não tem a forma esperada."""
    items: list[Item] = []
    categories = menu.get("categories") if isinstance(menu, dict) else None
    for cat in categories if isinstance(categories, list) else []:
        if not isinstance(cat, dict):
            continue
        products = cat.get("products")
        for product in products if isinstance(products, list) else []:
            if isinstance(product, dict) and product.get("name"):
                items.append(
                    Item(
                        str(cat.get("name", "")),
                        str(product["name"]),
                        to_price(product.get("price")),
                    )
                )
    return items


@dataclass
class MenuScore:
    tp: int = 0
    fp: int = 0
    fn: int = 0
    price_ok: int = 0
    price_total: int = 0
    category_ok: int = 0
    category_total: int = 0
    json_valid: bool = True
    exact: bool = False
    schema_errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def match(truth: list[Item], pred: list[Item]) -> list[tuple[int, int]]:
    """Casamento guloso pelos pares mais parecidos primeiro (nome exato antes do aproximado)."""
    pairs = []
    t_norm = [norm(t.name) for t in truth]
    p_norm = [norm(p.name) for p in pred]
    for i, tn in enumerate(t_norm):
        for j, pn in enumerate(p_norm):
            score = fuzz.token_sort_ratio(tn, pn)
            if score >= NAME_THRESHOLD:
                pairs.append((score, i, j))
    pairs.sort(key=lambda x: (-x[0], x[1], x[2]))
    used_t: set[int] = set()
    used_p: set[int] = set()
    matched = []
    for _, i, j in pairs:
        if i not in used_t and j not in used_p:
            used_t.add(i)
            used_p.add(j)
            matched.append((i, j))
    return matched


def score(truth: dict[str, Any], prediction: Any, inventory: bool = True) -> MenuScore:
    """Nota de um cardápio. `prediction=None` (sem JSON) perde todos os itens."""
    t_items = flatten(truth)
    if prediction is None:
        return MenuScore(fn=len(t_items), json_valid=False, schema_errors=["sem resposta"])
    errors = validate(prediction, inventory)
    p_items = flatten(prediction)
    matched = match(t_items, p_items)
    result = MenuScore(
        tp=len(matched),
        fp=len(p_items) - len(matched),
        fn=len(t_items) - len(matched),
        json_valid=not errors,
        schema_errors=errors[:5],
    )
    for i, j in matched:
        t, p = t_items[i], p_items[j]
        if t.price is not None:
            result.price_total += 1
            if p.price is not None and abs(p.price - t.price) < PRICE_TOLERANCE:
                result.price_ok += 1
        result.category_total += 1
        if fuzz.token_sort_ratio(norm(t.category), norm(p.category)) >= CATEGORY_THRESHOLD:
            result.category_ok += 1
    result.exact = (
        result.fp == 0
        and result.fn == 0
        and result.price_ok == result.price_total
        and result.category_ok == result.category_total
    )
    return result


def aggregate(scores: list[MenuScore]) -> dict[str, float]:
    """Soma os acertos de todos os cardápios (micro) e calcula as métricas finais."""
    tp = sum(s.tp for s in scores)
    fp = sum(s.fp for s in scores)
    fn = sum(s.fn for s in scores)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    price_total = sum(s.price_total for s in scores)
    category_total = sum(s.category_total for s in scores)
    return {
        "menus": len(scores),
        "item_precision": round(precision, 4),
        "item_recall": round(recall, 4),
        "item_f1": round(f1, 4),
        "price_accuracy": round(sum(s.price_ok for s in scores) / price_total, 4)
        if price_total
        else 0.0,
        "category_accuracy": round(sum(s.category_ok for s in scores) / category_total, 4)
        if category_total
        else 0.0,
        "hallucination_rate": round(fp / (tp + fp), 4) if tp + fp else 0.0,
        "json_valid_rate": round(sum(s.json_valid for s in scores) / len(scores), 4)
        if scores
        else 0.0,
        "exact_menu_rate": round(sum(s.exact for s in scores) / len(scores), 4) if scores else 0.0,
    }
