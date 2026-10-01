"""Executa um leitor sobre o conjunto, pontua cada cardápio e grava os resultados da execução."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from . import pricing
from .generate import load_index
from .metrics import MenuScore, aggregate, score
from .readers.base import Reader


class BudgetRequired(ValueError):
    """Leitor pago sem teto de gasto, ou sem preço conhecido para impor o teto."""


def _percentile(values: list[float], q: float) -> float:
    return round(float(np.percentile(values, q)), 3) if values else 0.0


def run(
    reader: Reader,
    data_dir: Path,
    run_id: str,
    runs_dir: Path = Path("runs"),
    limit: int | None = None,
    max_usd: float | None = None,
    inventory: bool = True,
    styles: list[str] | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if reader.paid:
        if max_usd is None:
            raise BudgetRequired("Leitor pago: informe --max-usd, o teto de gasto desta execução.")
        if pricing.find_model(reader.model) is None:
            raise BudgetRequired(
                f"O modelo '{reader.model}' não tem preço em pricing.json: sem preço não há como "
                "impor o teto. Acrescente o preço (com a fonte) e rode de novo."
            )
    index = load_index(data_dir)
    menus = [m for m in index["menus"] if not styles or m["style"] in styles]
    if limit:
        menus = menus[:limit]

    out_dir = runs_dir / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    records, scores = [], []
    by_style: dict[str, list[MenuScore]] = {}
    spent, unknown_price, stopped = 0.0, False, False

    with (out_dir / "menus.jsonl").open("w", encoding="utf-8") as sink:
        for entry in menus:
            # Para antes da chamada que provavelmente estouraria o teto, não depois. Só a primeira
            # leitura não tem estimativa: se ela sozinha custar mais que o teto, o teto é furado.
            average = spent / len(records) if records else 0.0
            if max_usd is not None and spent + average > max_usd:
                stopped = True
                break
            files = [data_dir / f for f in entry["files"]]
            truth = json.loads((data_dir / entry["truth"]).read_text(encoding="utf-8"))
            result = reader.read(files)
            menu_score = score(truth, result.menu, inventory)
            cost = pricing.cost_usd(result.model, result.usage)
            if cost is None and result.usage.input_tokens:
                unknown_price = True
            spent += cost or 0.0
            scores.append(menu_score)
            by_style.setdefault(entry["style"], []).append(menu_score)
            record = {
                "id": entry["id"],
                "style": entry["style"],
                "score": menu_score.as_dict(),
                "input_tokens": result.usage.input_tokens,
                "output_tokens": result.usage.output_tokens,
                "cached_input_tokens": result.usage.cached_input_tokens,
                "cost_usd": cost,
                "latency_s": round(result.latency_s, 3),
                "error": result.error,
                "prediction": result.menu,
            }
            records.append(record)
            sink.write(json.dumps(record, ensure_ascii=False) + "\n")

    n = len(records)
    costs = [r["cost_usd"] for r in records if r["cost_usd"] is not None]
    summary = {
        "run_id": run_id,
        "reader": reader.name,
        "model": reader.model,
        "config": {"inventory": inventory, **(config or {})},
        "dataset": {"dir": str(data_dir), "seed": index["seed"], "menus_total": index["count"]},
        "menus_run": n,
        "stopped_by_budget": stopped,
        "max_usd": max_usd,
        "spent_usd": round(spent, 6),
        "price_unknown": unknown_price,
        "overall": aggregate(scores),
        "by_style": {name: aggregate(s) for name, s in sorted(by_style.items())},
        "tokens_per_menu": {
            "input": round(sum(r["input_tokens"] for r in records) / n, 1) if n else 0,
            "output": round(sum(r["output_tokens"] for r in records) / n, 1) if n else 0,
        },
        "cost_per_menu_usd": round(sum(costs) / len(costs), 6) if costs else None,
        "latency_s": {
            "p50": _percentile([r["latency_s"] for r in records], 50),
            "p95": _percentile([r["latency_s"] for r in records], 95),
        },
        "errors": sum(1 for r in records if r["error"]),
    }
    (out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return summary
