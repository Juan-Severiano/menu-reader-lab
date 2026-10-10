"""Executa um leitor sobre o conjunto, pontua cada cardápio e grava os resultados da execução."""

from __future__ import annotations

import json
from collections.abc import Callable
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
    abort_after_errors: int = 4,
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
    records, scores, scores_tol = [], [], []
    by_style: dict[str, list[MenuScore]] = {}
    by_style_tol: dict[str, list[MenuScore]] = {}
    spent, unknown_price, stopped, aborted = 0.0, False, False, False
    failures_in_a_row = 0

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
            menu_score_tol = score(truth, result.menu, inventory, tolerant=True)
            cost = pricing.cost_usd(result.model, result.usage)
            if cost is None and result.usage.input_tokens:
                unknown_price = True
            spent += cost or 0.0
            scores.append(menu_score)
            scores_tol.append(menu_score_tol)
            by_style.setdefault(entry["style"], []).append(menu_score)
            by_style_tol.setdefault(entry["style"], []).append(menu_score_tol)
            record = {
                "id": entry["id"],
                "style": entry["style"],
                "score": menu_score.as_dict(),
                "score_tolerant": menu_score_tol.as_dict(),
                "input_tokens": result.usage.input_tokens,
                "output_tokens": result.usage.output_tokens,
                "cached_input_tokens": result.usage.cached_input_tokens,
                "reasoning_tokens": result.usage.reasoning_tokens,
                "cost_usd": cost,
                "latency_s": round(result.latency_s, 3),
                "error": result.error,
                "prediction": result.menu,
            }
            records.append(record)
            sink.write(json.dumps(record, ensure_ascii=False) + "\n")
            # Falha sem consumir token (modelo que recusa o pedido): não adianta insistir.
            failed_free = bool(result.error) and result.usage.input_tokens == 0
            failures_in_a_row = failures_in_a_row + 1 if failed_free else 0
            if abort_after_errors and failures_in_a_row >= abort_after_errors:
                aborted = True
                break

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
        "aborted_on_errors": aborted,
        "first_error": next((r["error"] for r in records if r["error"]), None),
        "max_usd": max_usd,
        "spent_usd": round(spent, 6),
        "price_unknown": unknown_price,
        "overall": aggregate(scores),
        "overall_tolerant": aggregate(scores_tol),
        "by_style": {name: aggregate(s) for name, s in sorted(by_style.items())},
        "by_style_tolerant": {name: aggregate(s) for name, s in sorted(by_style_tol.items())},
        "tokens_per_menu": {
            "input": round(sum(r["input_tokens"] for r in records) / n, 1) if n else 0,
            "output": round(sum(r["output_tokens"] for r in records) / n, 1) if n else 0,
            "reasoning": round(sum(r["reasoning_tokens"] for r in records) / n, 1) if n else 0,
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


def rescore(run_dir: Path, data_dir: Path, inventory: bool | None = None) -> dict[str, Any]:
    """Reavalia uma execução salva com o avaliador atual, sem chamar a API.

    Usa as leituras gravadas em `menus.jsonl`. Custo, tokens e latência não mudam; só as notas
    (estrita e tolerante) e os agregados são refeitos no `summary.json`.
    """
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    use_inventory = summary["config"]["inventory"] if inventory is None else inventory
    index = load_index(data_dir)
    style_of = {m["id"]: m["style"] for m in index["menus"]}
    truth_of = {m["id"]: m["truth"] for m in index["menus"]}
    scores, scores_tol = [], []
    by_style: dict[str, list[MenuScore]] = {}
    by_style_tol: dict[str, list[MenuScore]] = {}
    lines = []
    for line in (run_dir / "menus.jsonl").read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        truth = json.loads((data_dir / truth_of[record["id"]]).read_text(encoding="utf-8"))
        strict = score(truth, record["prediction"], use_inventory)
        tolerant = score(truth, record["prediction"], use_inventory, tolerant=True)
        record["score"], record["score_tolerant"] = strict.as_dict(), tolerant.as_dict()
        scores.append(strict)
        scores_tol.append(tolerant)
        by_style.setdefault(style_of[record["id"]], []).append(strict)
        by_style_tol.setdefault(style_of[record["id"]], []).append(tolerant)
        lines.append(json.dumps(record, ensure_ascii=False))
    (run_dir / "menus.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    summary["overall"] = aggregate(scores)
    summary["overall_tolerant"] = aggregate(scores_tol)
    summary["by_style"] = {n: aggregate(s) for n, s in sorted(by_style.items())}
    summary["by_style_tolerant"] = {n: aggregate(s) for n, s in sorted(by_style_tol.items())}
    (run_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return summary


def run_sweep(
    specs: list[str],
    reader_factory: Callable[[str, str | None], Reader],
    data_dir: Path,
    runs_dir: Path,
    prefix: str,
    tag: str,
    limit: int | None,
    max_usd_total: float,
    max_usd_each: float,
    inventory: bool = True,
    styles: list[str] | None = None,
    config: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Roda vários modelos sobre os mesmos cardápios, dividindo um teto total de gasto.

    Cada item de `specs` é `modelo` ou `modelo:esforço`. Cada modelo recebe no máximo
    `max_usd_each`, e nunca mais do que sobrou do total. Modelo sem preço é pulado e anotado.
    """
    remaining = max_usd_total
    results: list[dict[str, Any]] = []
    for spec in specs:
        model, _, effort = spec.partition(":")
        effort_or_none = effort or None
        # Abaixo de US$ 0,0001 o saldo é resíduo de arredondamento, não orçamento: a primeira
        # leitura de um modelo novo não tem estimativa e o estouraria.
        if remaining < 0.0001:
            results.append({"spec": spec, "skipped": "teto total esgotado"})
            continue
        run_id = f"{prefix}-{model}{'-' + effort if effort else ''}-{tag}"
        # Uma execução existente custou dinheiro: não se sobrescreve sem querer.
        if (runs_dir / run_id / "summary.json").exists():
            results.append({"spec": spec, "skipped": f"a execução {run_id} já existe"})
            continue
        try:
            summary = run(
                reader_factory(model, effort_or_none),
                data_dir,
                run_id,
                runs_dir,
                limit,
                min(max_usd_each, remaining),
                inventory,
                styles,
                {**(config or {}), "reasoning_effort": effort_or_none},
            )
        except BudgetRequired as exc:
            results.append({"spec": spec, "skipped": str(exc)})
            continue
        remaining = round(remaining - summary["spent_usd"], 6)
        results.append({"spec": spec, "summary": summary})
    return results
