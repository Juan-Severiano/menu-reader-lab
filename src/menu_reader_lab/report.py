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
        "| Execução | Leitor | Menus | F1 de itens | F1 tolerante | Precisão | Revocação | "
        "Preço certo | "
        "Inventado | JSON válido | Tokens (entrada/saída) | US$ por cardápio | p50 / p95 (s) |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for s in sorted(summaries, key=lambda x: -x["overall"]["item_f1"]):
        o, t, lat = s["overall"], s["tokens_per_menu"], s["latency_s"]
        rows.append(
            f"| {s['run_id']} | {s['reader']} `{s['model']}` | {s['menus_run']} | "
            f"{_fmt(o['item_f1'])} | {_fmt(s.get('overall_tolerant', {}).get('item_f1'))} | "
            f"{_fmt(o['item_precision'])} | {_fmt(o['item_recall'])} | "
            f"{_fmt(o['price_accuracy'])} | {_fmt(o['hallucination_rate'])} | "
            f"{_fmt(o['json_valid_rate'])} | {t['input']:.0f} / {t['output']:.0f} | "
            f"{_fmt(s['cost_per_menu_usd'], 5)} | {_fmt(lat['p50'], 2)} / {_fmt(lat['p95'], 2)} |"
        )
    return "\n".join(rows)


def style_table(summary: dict[str, Any]) -> str:
    rows = [
        f"**{summary['run_id']}**: F1 de itens por estilo de cardápio",
        "",
        "| Estilo | Menus | F1 | F1 tolerante | Preço certo | Inventado |",
        "|---|---|---|---|---|---|",
    ]
    tolerant = summary.get("by_style_tolerant", {})
    for name, o in summary["by_style"].items():
        rows.append(
            f"| {name} | {o['menus']} | {_fmt(o['item_f1'])} | "
            f"{_fmt(tolerant.get(name, {}).get('item_f1'))} | "
            f"{_fmt(o['price_accuracy'])} | {_fmt(o['hallucination_rate'])} |"
        )
    return "\n".join(rows)


def _label(summary: dict[str, Any]) -> str:
    effort = (summary.get("config") or {}).get("reasoning_effort")
    return f"{summary['model']} ({effort})" if effort else summary["model"]


def scatter(summaries: list[dict[str, Any]], path: Path) -> bool:
    """Qualidade (F1) contra custo por cardápio. Só entram execuções com custo medido."""
    points = [
        (s["cost_per_menu_usd"], s["overall"]["item_f1"], _label(s))
        for s in summaries
        if s["cost_per_menu_usd"]
    ]
    if len(points) < 2:
        return False
    fig, ax = plt.subplots(figsize=(7.2, 4.4))
    # Rótulos que caem no mesmo lugar sobem em degraus, em vez de se sobrepor.
    placed: list[tuple[float, float]] = []
    for cost, f1, label in sorted(points):
        ax.scatter(cost, f1)
        step = sum(1 for c, f in placed if abs(f - f1) < 0.004 and c * 3 > cost)
        ax.annotate(
            label,
            (cost, f1),
            textcoords="offset points",
            xytext=(6, 5 + 11 * step),
            fontsize=8,
        )
        placed.append((cost, f1))
    ax.set_xscale("log")
    ax.set_ylim(top=max(f1 for _, f1, _ in points) + 0.006)
    ax.set_xlabel("US$ por cardápio (escala log)")
    ax.set_ylabel("F1 de itens (estrito; eixo cortado)")
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
