import json
from types import SimpleNamespace

import pytest
from PIL import Image

from menu_reader_lab.metrics import norm
from menu_reader_lab.prepare import pdf_text, shrink_image
from menu_reader_lab.readers.openai_reader import OpenAIReader
from menu_reader_lab.runner import run_sweep


class Recorder:
    def __init__(self):
        self.calls = []

    @property
    def responses(self):
        return self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            output_text="{}",
            usage=SimpleNamespace(
                input_tokens=10,
                output_tokens=10,
                input_tokens_details=SimpleNamespace(cached_tokens=0),
                output_tokens_details=SimpleNamespace(reasoning_tokens=0),
            ),
        )


def first(data_dir, style, pattern):
    return next(data_dir.glob(f"*{style}/{pattern}"))


def kinds(recorder):
    return [item["type"] for item in recorder.calls[0]["input"][0]["content"]]


def test_shrink_reduces_the_longest_side_and_never_enlarges(tmp_path):
    big, small = tmp_path / "big.png", tmp_path / "small.png"
    Image.new("RGB", (3000, 2000), "white").save(big)
    Image.new("RGB", (400, 300), "white").save(small)
    data, mime = shrink_image(big, 1000)
    assert mime == "image/jpeg"
    out = tmp_path / "out.jpg"
    out.write_bytes(data)
    assert Image.open(out).size == (1000, 667)
    # imagem que já cabe volta intacta, sem recomprimir
    assert shrink_image(small, 1000) == (small.read_bytes(), "image/png")


def test_shrink_rejects_a_non_positive_limit(tmp_path):
    path = tmp_path / "a.png"
    Image.new("RGB", (10, 10)).save(path)
    with pytest.raises(ValueError):
        shrink_image(path, 0)


def test_digital_pdf_text_keeps_every_item_name(data_dir):
    for style in ("pdf_digital_clean", "pdf_digital_2col"):
        pdf = first(data_dir, style, "menu.pdf")
        truth = json.loads(pdf.with_name("truth.json").read_text(encoding="utf-8"))
        text = norm(pdf_text(pdf))
        names = [p["name"] for c in truth["categories"] for p in c["products"]]
        assert all(norm(name) in text for name in names), style


def test_scanned_pdf_has_no_useful_text(data_dir):
    assert pdf_text(first(data_dir, "pdf_scan", "menu.pdf")) is None


def test_pdf_goes_as_text_only_when_asked_and_when_it_has_text(data_dir):
    digital = first(data_dir, "pdf_digital_clean", "menu.pdf")
    scan = first(data_dir, "pdf_scan", "menu.pdf")
    off, on_digital, on_scan = Recorder(), Recorder(), Recorder()
    OpenAIReader(client=off).read([digital])
    OpenAIReader(pdf_as_text=True, client=on_digital).read([digital])
    OpenAIReader(pdf_as_text=True, client=on_scan).read([scan])
    assert kinds(off) == ["input_text", "input_file"]
    assert kinds(on_digital) == ["input_text", "input_text"]
    assert kinds(on_scan) == ["input_text", "input_file"]


def test_max_side_shrinks_the_photo_sent_to_the_api(data_dir):
    photo = sorted(data_dir.glob("*photo_straight/*.jpg"))[0]
    full, small = Recorder(), Recorder()
    OpenAIReader(client=full).read([photo])
    OpenAIReader(max_side=600, client=small).read([photo])

    def sent(rec):
        return len(rec.calls[0]["input"][0]["content"][1]["image_url"])

    assert sent(small) < sent(full) / 2


def test_sweep_does_not_overwrite_an_existing_run(data_dir, tmp_path):
    def factory(model, effort):
        return OpenAIReader(model=model, client=Recorder())

    args = (["gpt-4.1-mini"], factory, data_dir, tmp_path, "t", "high", 1, 1.0, 1.0)
    first_pass = run_sweep(*args)
    again = run_sweep(*args)
    assert "summary" in first_pass[0]
    assert "já existe" in again[0]["skipped"]
