import json

import pytest

from menu_reader_lab.readers.base import ReadResult, Usage
from menu_reader_lab.readers.oracle import NoisyReader, OracleReader
from menu_reader_lab.runner import BudgetRequired, run


def test_oracle_scores_perfectly_on_every_style(data_dir, tmp_path):
    summary = run(OracleReader(), data_dir, "oracle", tmp_path)
    o = summary["overall"]
    assert summary["menus_run"] == 10
    assert (o["item_f1"], o["price_accuracy"], o["category_accuracy"]) == (1.0, 1.0, 1.0)
    assert o["hallucination_rate"] == 0.0 and o["json_valid_rate"] == 1.0
    assert o["exact_menu_rate"] == 1.0


def test_noisy_reader_score_follows_the_noise_applied(data_dir, tmp_path):
    clean = run(
        NoisyReader(drop=0.0, price_error=0.0, rename=0.0, invent=0.0), data_dir, "n0", tmp_path
    )["overall"]
    light = run(
        NoisyReader(drop=0.1, price_error=0.1, rename=0.05, invent=0.05), data_dir, "n1", tmp_path
    )["overall"]
    heavy = run(
        NoisyReader(drop=0.4, price_error=0.4, rename=0.2, invent=0.2), data_dir, "n2", tmp_path
    )["overall"]
    assert clean["item_f1"] == 1.0
    assert clean["item_f1"] > light["item_f1"] > heavy["item_f1"]
    assert clean["price_accuracy"] > light["price_accuracy"] > heavy["price_accuracy"]
    # perder ~10% dos itens tem que aparecer como revocação perto de 0,9
    assert 0.8 < light["item_recall"] < 0.97
    assert heavy["hallucination_rate"] > light["hallucination_rate"] > 0


def test_results_are_written_to_disk(data_dir, tmp_path):
    run(OracleReader(), data_dir, "disk", tmp_path, limit=2)
    summary = json.loads((tmp_path / "disk" / "summary.json").read_text(encoding="utf-8"))
    lines = (tmp_path / "disk" / "menus.jsonl").read_text(encoding="utf-8").splitlines()
    assert summary["menus_run"] == 2 and len(lines) == 2
    assert set(json.loads(lines[0])) >= {"score", "cost_usd", "latency_s", "prediction"}


def test_by_style_breakdown_covers_every_style(data_dir, tmp_path):
    summary = run(OracleReader(), data_dir, "styles", tmp_path)
    assert len(summary["by_style"]) == 10


class PaidFake:
    """Leitor pago de mentira: cada leitura custa US$ 1,50 (gpt-4.1)."""

    name, model, paid = "fake-paid", "gpt-4.1", True

    def __init__(self):
        self.calls = 0

    def read(self, files):
        self.calls += 1
        return ReadResult(menu=None, usage=Usage(750_000, 0), model=self.model, latency_s=0.1)


def test_paid_reader_without_a_budget_is_refused(data_dir, tmp_path):
    reader = PaidFake()
    with pytest.raises(BudgetRequired):
        run(reader, data_dir, "no-budget", tmp_path)
    assert reader.calls == 0


def test_budget_stops_before_the_call_that_would_exceed_it(data_dir, tmp_path):
    reader = PaidFake()
    summary = run(reader, data_dir, "budget", tmp_path, max_usd=2.0)
    # Depois da 1ª leitura (US$ 1,50) a próxima custaria ~1,50 e passaria de 2,00: para ali.
    assert reader.calls == 1 and summary["stopped_by_budget"]
    assert summary["spent_usd"] == pytest.approx(1.5) and summary["spent_usd"] <= 2.0


def test_budget_lets_the_run_use_the_whole_allowance(data_dir, tmp_path):
    reader = PaidFake()
    summary = run(reader, data_dir, "budget-wide", tmp_path, max_usd=4.5)
    assert reader.calls == 3 and summary["spent_usd"] == pytest.approx(4.5)
    assert summary["stopped_by_budget"]


def test_paid_reader_with_an_unpriced_model_is_refused(data_dir, tmp_path):
    reader = PaidFake()
    reader.model = "modelo-sem-preco"
    with pytest.raises(BudgetRequired, match="sem preço|não tem preço"):
        run(reader, data_dir, "unpriced", tmp_path, max_usd=5.0)
    assert reader.calls == 0
