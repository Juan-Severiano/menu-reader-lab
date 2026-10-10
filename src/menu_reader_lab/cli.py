"""Linha de comando: gerar o conjunto, rodar um leitor, varrer modelos e montar o relatório."""

from __future__ import annotations

import argparse
from pathlib import Path

from .generate import generate_dataset
from .readers.base import Reader
from .report import write_report
from .runner import BudgetRequired, rescore, run, run_sweep


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

        return OpenAIReader(
            model=args.model or "gpt-4.1",
            detail=args.detail,
            inventory=inventory,
            max_output_tokens=args.max_output_tokens,
            reasoning_effort=args.reasoning_effort,
        )
    raise SystemExit(f"Leitor desconhecido: {args.reader}")


def _print_run(summary: dict) -> None:
    o = summary["overall"]
    flag = " | PAROU PELO TETO" if summary.get("stopped_by_budget") else ""
    flag += " | ABORTOU POR ERROS" if summary.get("aborted_on_errors") else ""
    print(
        f"{summary['run_id']}: {summary['menus_run']} cardápios | F1 {o['item_f1']} "
        f"(tolerante {summary['overall_tolerant']['item_f1']}) | "
        f"preço {o['price_accuracy']} | inventado {o['hallucination_rate']} | "
        f"erros {summary['errors']} | US$ {summary['spent_usd']}{flag}"
    )
    if summary.get("first_error"):
        print(f"    primeiro erro: {summary['first_error']}")


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
    runp.add_argument("--reasoning-effort", help="esforço de raciocínio (none, low, medium, ...)")
    runp.add_argument("--max-output-tokens", type=int, help="limite de saída (padrão automático)")
    runp.add_argument("--noise", type=float, default=0.1, help="intensidade do leitor ruidoso")
    runp.add_argument("--no-inventory", action="store_true", help="sem o inventário `sections`")
    runp.add_argument("--limit", type=int, help="só os N primeiros cardápios")
    runp.add_argument("--styles", nargs="*", help="só estes estilos")
    runp.add_argument("--max-usd", type=float, help="teto de gasto (obrigatório em leitor pago)")

    sweep = sub.add_parser("sweep", help="roda vários modelos da OpenAI sob um teto total")
    sweep.add_argument(
        "--models", nargs="+", required=True, help="modelo ou modelo:esforço, ex.: gpt-6-luna:low"
    )
    sweep.add_argument("--max-usd-total", type=float, required=True)
    sweep.add_argument("--max-usd-each", type=float, help="teto por modelo (padrão: o total)")
    sweep.add_argument("--limit", type=int, help="só os N primeiros cardápios")
    sweep.add_argument("--styles", nargs="*", help="só estes estilos")
    sweep.add_argument("--detail", default="high", choices=["low", "high", "auto"])
    sweep.add_argument("--max-output-tokens", type=int)
    sweep.add_argument("--no-inventory", action="store_true")
    sweep.add_argument("--prefix", default="openai", help="início do nome de cada execução")
    sweep.add_argument("--data", type=Path, default=Path("data/synthetic"))
    sweep.add_argument("--runs", type=Path, default=Path("runs"))

    rescorep = sub.add_parser(
        "rescore", help="reavalia execuções salvas com o avaliador atual, sem chamar a API"
    )
    rescorep.add_argument("--runs", type=Path, default=Path("runs"))
    rescorep.add_argument("--data", type=Path, default=Path("data/synthetic"))
    rescorep.add_argument("--only", nargs="*", help="só estas execuções (nome da pasta)")

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
                {"detail": args.detail, "reasoning_effort": args.reasoning_effort}
                if args.reader == "openai"
                else None,
            )
        except BudgetRequired as exc:
            raise SystemExit(str(exc)) from exc
        _print_run(summary)
    elif args.command == "sweep":
        from .readers.openai_reader import OpenAIReader

        def factory(model: str, effort: str | None) -> Reader:
            return OpenAIReader(
                model=model,
                detail=args.detail,
                inventory=not args.no_inventory,
                max_output_tokens=args.max_output_tokens,
                reasoning_effort=effort,
            )

        results = run_sweep(
            args.models,
            factory,
            args.data,
            args.runs,
            args.prefix,
            args.detail,
            args.limit,
            args.max_usd_total,
            args.max_usd_each or args.max_usd_total,
            not args.no_inventory,
            args.styles,
            {"detail": args.detail},
        )
        total = 0.0
        for item in results:
            if "skipped" in item:
                print(f"{item['spec']}: PULADO ({item['skipped']})")
            else:
                _print_run(item["summary"])
                total += item["summary"]["spent_usd"]
        print(f"gasto total da varredura: US$ {total:.4f} (teto US$ {args.max_usd_total})")
    elif args.command == "rescore":
        for run_dir in sorted(p for p in args.runs.iterdir() if (p / "menus.jsonl").exists()):
            if args.only and run_dir.name not in args.only:
                continue
            if (run_dir / "summary.json").exists():
                _print_run(rescore(run_dir, args.data))
    else:
        print(write_report(args.runs, args.out))


if __name__ == "__main__":
    main()
