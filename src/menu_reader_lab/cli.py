"""Linha de comando: gerar o conjunto, rodar um leitor e montar o relatório."""

from __future__ import annotations

import argparse
from pathlib import Path

from .generate import generate_dataset
from .readers.base import Reader
from .report import write_report
from .runner import BudgetRequired, run


def make_reader(args: argparse.Namespace) -> Reader:
    inventory = not args.no_inventory
    if args.reader == "oracle":
        from .readers.oracle import OracleReader

        return OracleReader(inventory=inventory)
    if args.reader == "noisy":
        from .readers.oracle import NoisyReader

        return NoisyReader(
            drop=args.noise,
            price_error=args.noise,
            rename=args.noise / 2,
            invent=args.noise / 2,
            inventory=inventory,
        )
    if args.reader == "openai":
        from .readers.openai_reader import OpenAIReader

        return OpenAIReader(model=args.model or "gpt-4.1", detail=args.detail, inventory=inventory)
    raise SystemExit(f"Leitor desconhecido: {args.reader}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="menu-lab", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    gen = sub.add_parser("generate", help="gera cardápios sintéticos com gabarito")
    gen.add_argument("--n", type=int, default=60)
    gen.add_argument("--seed", type=int, default=7)
    gen.add_argument("--out", type=Path, default=Path("data/synthetic"))

    runp = sub.add_parser("run", help="roda um leitor sobre o conjunto")
    runp.add_argument("--reader", choices=["oracle", "noisy", "openai"], required=True)
    runp.add_argument("--run-id", required=True)
    runp.add_argument("--data", type=Path, default=Path("data/synthetic"))
    runp.add_argument("--runs", type=Path, default=Path("runs"))
    runp.add_argument("--model", help="modelo do leitor pago (padrão: gpt-4.1)")
    runp.add_argument("--detail", default="high", choices=["low", "high", "auto"])
    runp.add_argument("--noise", type=float, default=0.1, help="intensidade do leitor ruidoso")
    runp.add_argument("--no-inventory", action="store_true", help="sem o inventário `sections`")
    runp.add_argument("--limit", type=int, help="só os N primeiros cardápios")
    runp.add_argument("--styles", nargs="*", help="só estes estilos")
    runp.add_argument("--max-usd", type=float, help="teto de gasto (obrigatório em leitor pago)")

    rep = sub.add_parser("report", help="monta o relatório das execuções")
    rep.add_argument("--runs", type=Path, default=Path("runs"))
    rep.add_argument("--out", type=Path, default=Path("runs/results.md"))

    args = parser.parse_args(argv)
    if args.command == "generate":
        entries = generate_dataset(args.out, args.n, args.seed)
        print(f"{len(entries)} cardápios em {args.out} (semente {args.seed})")
    elif args.command == "run":
        if args.reader == "openai" and args.max_usd is None:
            raise SystemExit("Leitor pago: informe --max-usd, o teto de gasto desta execução.")
        try:
            summary = run(
                make_reader(args),
                args.data,
                args.run_id,
                args.runs,
                args.limit,
                args.max_usd,
                not args.no_inventory,
                args.styles,
                {"detail": args.detail} if args.reader == "openai" else None,
            )
        except BudgetRequired as exc:
            raise SystemExit(str(exc)) from exc
        o = summary["overall"]
        print(
            f"{summary['run_id']}: {summary['menus_run']} cardápios | F1 {o['item_f1']} | "
            f"preço {o['price_accuracy']} | inventado {o['hallucination_rate']} | "
            f"US$ {summary['spent_usd']}"
        )
    else:
        print(write_report(args.runs, args.out))


if __name__ == "__main__":
    main()
