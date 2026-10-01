import json
from types import SimpleNamespace

import pytest

from menu_reader_lab import pricing
from menu_reader_lab.readers.base import Usage
from menu_reader_lab.readers.openai_reader import OpenAIReader
from menu_reader_lab.schema import build_schema, truth_to_menu


def test_cost_of_gpt_4_1_without_cache():
    # 8 mil tokens de entrada a US$ 2 e 7 mil de saída a US$ 8 por milhão
    cost = pricing.cost_usd("gpt-4.1", Usage(input_tokens=8000, output_tokens=7000))
    assert cost == pytest.approx(8000 * 2 / 1e6 + 7000 * 8 / 1e6)


def test_cached_tokens_use_the_cached_rate():
    usage = Usage(input_tokens=10_000, output_tokens=0, cached_input_tokens=6_000)
    assert pricing.cost_usd("gpt-4.1", usage) == pytest.approx(4000 * 2 / 1e6 + 6000 * 0.5 / 1e6)


def test_dated_model_names_resolve_to_the_base_price():
    usage = Usage(input_tokens=1_000_000)
    assert pricing.cost_usd("gpt-4.1-2025-04-14", usage) == pytest.approx(2.0)
    # o mais específico vence: mini não pode virar gpt-4.1
    assert pricing.cost_usd("gpt-4.1-mini-2025-04-14", usage) == pytest.approx(0.4)


def test_unknown_model_has_no_price_instead_of_a_guess():
    assert pricing.cost_usd("modelo-que-nao-existe", Usage(input_tokens=1000)) is None


def test_every_price_has_a_source_and_positive_rates():
    for name, price in pricing.table()["models"].items():
        assert price["source"].startswith("http"), name
        assert price["input"] > 0 and price["output"] > 0, name


class FakeResponses:
    def __init__(self, output_text):
        self.output_text = output_text
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            output_text=self.output_text,
            usage=SimpleNamespace(
                input_tokens=1200,
                output_tokens=300,
                input_tokens_details=SimpleNamespace(cached_tokens=200),
            ),
        )


def fake_client(output_text):
    return SimpleNamespace(responses=FakeResponses(output_text))


def test_openai_request_has_strict_schema_images_and_detail(data_dir):
    menu_dir = next(p for p in data_dir.iterdir() if p.name.endswith("photo_straight"))
    files = sorted(menu_dir.glob("menu-*.jpg"))
    truth = json.loads((menu_dir / "truth.json").read_text(encoding="utf-8"))
    client = fake_client(json.dumps(truth_to_menu(truth)))
    result = OpenAIReader(model="gpt-4.1", detail="low", client=client).read(files)

    call = client.responses.calls[0]
    assert call["model"] == "gpt-4.1" and call["store"] is False
    fmt = call["text"]["format"]
    assert fmt["type"] == "json_schema" and fmt["strict"] is True
    assert fmt["schema"] == build_schema(True)
    content = call["input"][0]["content"]
    assert content[0]["type"] == "input_text"
    images = [c for c in content if c["type"] == "input_image"]
    assert len(images) == len(files)
    assert all(
        i["detail"] == "low" and i["image_url"].startswith("data:image/jpeg;base64,")
        for i in images
    )
    assert result.error is None and result.menu == truth_to_menu(truth)
    assert result.usage == Usage(1200, 300, 200)


def test_openai_sends_pdf_as_a_file(data_dir):
    pdf = next(data_dir.glob("*pdf_digital_clean/menu.pdf"))
    client = fake_client("{}")
    OpenAIReader(client=client).read([pdf])
    part = client.responses.calls[0]["input"][0]["content"][1]
    assert part["type"] == "input_file" and part["filename"] == "menu.pdf"
    assert part["file_data"].startswith("data:application/pdf;base64,")


def test_no_inventory_changes_schema_and_request(data_dir):
    pdf = next(data_dir.glob("*pdf_digital_clean/menu.pdf"))
    client = fake_client("{}")
    OpenAIReader(inventory=False, client=client).read([pdf])
    call = client.responses.calls[0]
    assert "sections" not in call["text"]["format"]["schema"]["properties"]


def test_invalid_json_becomes_an_error_with_usage_kept(data_dir):
    pdf = next(data_dir.glob("*pdf_digital_clean/menu.pdf"))
    result = OpenAIReader(client=fake_client("isso não é json")).read([pdf])
    assert result.menu is None and result.error == "resposta não é JSON"
    assert result.usage.input_tokens == 1200  # a API cobra mesmo assim


def test_api_failure_becomes_data_not_a_crash(data_dir):
    class Boom:
        class responses:  # noqa: N801
            @staticmethod
            def create(**_):
                raise TimeoutError("demorou")

    pdf = next(data_dir.glob("*pdf_digital_clean/menu.pdf"))
    result = OpenAIReader(client=Boom()).read([pdf])
    assert result.menu is None and result.error.startswith("TimeoutError")
