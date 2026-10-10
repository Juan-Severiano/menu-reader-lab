import json
from types import SimpleNamespace

import pytest

from menu_reader_lab import pricing
from menu_reader_lab.readers.base import ReadResult, Usage
from menu_reader_lab.readers.openai_reader import OpenAIReader
from menu_reader_lab.runner import run, run_sweep
from menu_reader_lab.schema import truth_to_menu


class Recorder:
    """Cliente falso que guarda os pedidos e devolve uma resposta configurável."""

    def __init__(self, **response):
        self.calls = []
        self.response = response

    @property
    def responses(self):
        return self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(**self.response)


def answer(text, reasoning=0, **extra):
    return {
        "output_text": text,
        "usage": SimpleNamespace(
            input_tokens=1000,
            output_tokens=4000 + reasoning,
            input_tokens_details=SimpleNamespace(cached_tokens=0),
            output_tokens_details=SimpleNamespace(reasoning_tokens=reasoning),
        ),
        **extra,
    }


@pytest.fixture
def pdf(data_dir):
    return next(data_dir.glob("*pdf_digital_clean/menu.pdf"))


def test_reasoning_effort_is_sent_only_when_asked(pdf):
    with_effort, without = Recorder(**answer("{}")), Recorder(**answer("{}"))
    OpenAIReader(model="gpt-6-luna", reasoning_effort="low", client=with_effort).read([pdf])
    OpenAIReader(model="gpt-4.1", client=without).read([pdf])
    assert with_effort.calls[0]["reasoning"] == {"effort": "low"}
    assert "reasoning" not in without.calls[0]


def test_output_limit_leaves_room_for_reasoning():
    assert OpenAIReader(client=object()).max_output_tokens == 16000
    assert OpenAIReader(reasoning_effort="none", client=object()).max_output_tokens == 16000
    assert OpenAIReader(reasoning_effort="low", client=object()).max_output_tokens == 32000
    assert (
        OpenAIReader(reasoning_effort="low", max_output_tokens=5, client=object()).max_output_tokens
        == 5
    )


def test_reasoning_tokens_are_read_from_usage(pdf, data_dir):
    result = OpenAIReader(
        reasoning_effort="low", client=Recorder(**answer("{}", reasoning=2500))
    ).read([pdf])
    assert result.usage.reasoning_tokens == 2500
    assert result.usage.output_tokens == 6500  # o raciocínio já está dentro da saída cobrada


def test_incomplete_response_is_an_explicit_error_and_keeps_the_bill(pdf):
    client = Recorder(
        **answer(
            '{"categories": [',
            reasoning=3000,
            status="incomplete",
            incomplete_details=SimpleNamespace(reason="max_output_tokens"),
        )
    )
    result = OpenAIReader(reasoning_effort="low", client=client).read([pdf])
    assert result.menu is None
    assert result.error == "resposta incompleta (max_output_tokens)"
    assert result.usage.output_tokens == 7000  # a API cobra mesmo assim


class Failing:
    """Leitor que recusa tudo sem consumir token, como um modelo que não aceita o pedido."""

    name, model, paid = "fail", "gpt-6-luna", True

    def __init__(self):
        self.calls = 0

    def read(self, files):
        self.calls += 1
        return ReadResult(
            menu=None, model=self.model, error="BadRequestError: sem suporte a imagem"
        )


def test_run_aborts_after_repeated_free_failures(data_dir, tmp_path):
    reader = Failing()
    summary = run(reader, data_dir, "abort", tmp_path, max_usd=1.0)
    assert reader.calls == 4 and summary["aborted_on_errors"]
    assert summary["first_error"].startswith("BadRequestError")
    assert summary["spent_usd"] == 0


class Alternating:
    """Falha sem custo, depois acerta, e repete: nunca são 4 falhas seguidas."""

    name, model, paid = "alt", "gpt-6-luna", True

    def __init__(self):
        self.calls = 0

    def read(self, files):
        self.calls += 1
        if self.calls % 2:
            return ReadResult(menu=None, model=self.model, error="falha")
        truth = json.loads((files[0].parent / "truth.json").read_text(encoding="utf-8"))
        return ReadResult(menu=truth_to_menu(truth), model=self.model, usage=Usage(1000, 1000))


def test_a_success_resets_the_failure_counter(data_dir, tmp_path):
    reader = Alternating()
    summary = run(reader, data_dir, "alt", tmp_path, max_usd=1.0)
    assert reader.calls == 10 and not summary["aborted_on_errors"]


class Priced:
    """Cada leitura custa US$ 0,01 no preço do gpt-6-luna (100 mil tokens de entrada)."""

    name, paid = "priced", True

    def __init__(self, model):
        self.model = model

    def read(self, files):
        truth = json.loads((files[0].parent / "truth.json").read_text(encoding="utf-8"))
        return ReadResult(menu=truth_to_menu(truth), model=self.model, usage=Usage(100_000, 0))


def factory(model, effort):
    return Priced(model)


def test_sweep_gives_each_model_its_share_and_never_passes_the_total(data_dir, tmp_path):
    results = run_sweep(
        ["gpt-6-luna", "gpt-6-luna:low", "gpt-4.1-nano"],
        factory,
        data_dir,
        tmp_path,
        prefix="t",
        tag="high",
        limit=10,
        max_usd_total=0.05,
        max_usd_each=0.03,
    )
    spent = [r["summary"]["spent_usd"] for r in results if "summary" in r]
    # cada modelo para antes de passar do próprio teto (US$ 0,03 = 3 leituras de US$ 0,01)
    assert spent[0] == pytest.approx(0.03) and spent[1] == pytest.approx(0.02)
    assert sum(spent) <= 0.05 + 1e-9
    assert results[2] == {"spec": "gpt-4.1-nano", "skipped": "teto total esgotado"}


def test_sweep_names_runs_after_model_effort_and_detail(data_dir, tmp_path):
    results = run_sweep(
        ["gpt-6-luna:low"],
        factory,
        data_dir,
        tmp_path,
        prefix="openai",
        tag="high",
        limit=1,
        max_usd_total=1,
        max_usd_each=1,
    )
    assert results[0]["summary"]["run_id"] == "openai-gpt-6-luna-low-high"
    assert results[0]["summary"]["config"]["reasoning_effort"] == "low"


def test_sweep_skips_a_model_without_a_price_and_goes_on(data_dir, tmp_path):
    results = run_sweep(
        ["modelo-sem-preco", "gpt-6-luna"],
        factory,
        data_dir,
        tmp_path,
        prefix="t",
        tag="x",
        limit=1,
        max_usd_total=1,
        max_usd_each=1,
    )
    assert "sem preço" in results[0]["skipped"] or "não tem preço" in results[0]["skipped"]
    assert results[1]["summary"]["menus_run"] == 1


def test_cheap_openai_models_are_priced_with_a_source():
    for name in ["gpt-6-luna", "gpt-5.6-luna", "gpt-5.4-nano", "gpt-5-nano", "gpt-4.1-nano"]:
        price = pricing.find_model(name)
        assert price and price["source"].startswith("https://developers.openai.com"), name
    luna = pricing.find_model("gpt-6-luna")
    assert (luna["input"], luna["output"]) == (0.10, 0.50)
    # o mais específico vence: gpt-5.4-nano não pode virar outro modelo
    assert pricing.find_model("gpt-5.4-nano-2026-01-01")["output"] == 1.25
