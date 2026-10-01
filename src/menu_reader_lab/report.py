"""Relatório em Markdown e gráfico de qualidade contra custo, a partir dos `summary.json`."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


def load_summaries(runs_dir: Path) -> list[dict[str, Any]]:
    return [
        json.loads(p.read_text(encoding="utf-8")) for p in sorted(runs_dir.glob("*/summary.json"))
    ]


def _fmt(value: float | None, digits: int = 4) -> str:
    return "n/d" if value is None else f"{value:.{digits}f}".replace(".", ",")


def table(summaries: list[dict[str, Any]]) -> str:
    rows = [
        "| Execução | Leitor | Menus | F1 de itens | Precisão | Revocação | Preço certo | "
        "Inventado | JSON válido | Tokens (entrada/saída) | US$ por cardápio | p50 / p95 (s) |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for s in sorted(summaries, key=lambda x: -x["overall"]["item_f1"]):
        o, t, lat = s["overall"], s["tokens_per_menu"], s["latency_s"]
        rows.append(
            f"| {s['run_id']} | {s['reader']} `{s['model']}` | {s['menus_run']} | "
            f"{_fmt(o['item_f1'])} | {_fmt(o['item_precision'])} | {_fmt(o['item_recall'])} | "
            f"{_fmt(o['price_accuracy'])} | {_fmt(o['hallucination_rate'])} | "
            f"{_fmt(o['json_valid_rate'])} | {t['input']:.0f} / {t['output']:.0f} | "
            f"{_fmt(s['cost_per_menu_usd'], 5)} | {_fmt(lat['p50'], 2)} / {_fmt(lat['p95'], 2)} |"
        )
    return "\n".join(rows)


def style_table(summary: dict[str, Any]) -> str:
    rows = [
        f"**{summary['run_id']}**: F1 de itens por estilo de cardápio",
        "",
        "| Estilo | Menus | F1 | Preço certo | Inventado |",
        "|---|---|---|---|---|",
    ]
    for name, o in summary["by_style"].items():
        rows.append(
            f"| {name} | {o['menus']} | {_fmt(o['item_f1'])} | "
            f"{_fmt(o['price_accuracy'])} | {_fmt(o['hallucination_rate'])} |"
        )
    return "\n".join(rows)


def scatter(summaries: list[dict[str, Any]], path: Path) -> bool:
    """Qualidade (F1) contra custo por cardápio. Só entram execuções com custo medido."""
    points = [
        (s["cost_per_menu_usd"], s["overall"]["item_f1"], f"{s['reader']} {s['model']}")
        for s in summaries
        if s["cost_per_menu_usd"]
    ]
    if len(points) < 2:
        return False
    fig, ax = plt.subplots(figsize=(6.5, 4.2))
    for cost, f1, label in points:
        ax.scatter(cost, f1)
        ax.annotate(label, (cost, f1), textcoords="offset points", xytext=(6, 4), fontsize=8)
    ax.set_xscale("log")
    ax.set_xlabel("US$ por cardápio (escala log)")
    ax.set_ylabel("F1 de itens")
    ax.set_title("Qualidade contra custo")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return True


def write_report(runs_dir: Path, out: Path) -> str:
    summaries = load_summaries(runs_dir)
    if not summaries:
        raise SystemExit(f"Nenhuma execução em {runs_dir}.")
    parts = ["# Resultados", "", table(summaries), ""]
    for s in summaries:
        parts += [style_table(s), ""]
    chart = out.with_suffix(".png")
    if scatter(summaries, chart):
        parts += [f"![Qualidade contra custo]({chart.name})", ""]
    out.write_text("\n".join(parts), encoding="utf-8")
    return str(out)
