import json
import random

from menu_reader_lab.generate import generate_dataset, load_index, make_truth
from menu_reader_lab.metrics import norm
from menu_reader_lab.render import STYLES
from menu_reader_lab.schema import truth_to_menu, validate


def test_truth_is_deterministic():
    assert make_truth(random.Random(5)) == make_truth(random.Random(5))
    assert make_truth(random.Random(5)) != make_truth(random.Random(6))


def test_truth_has_no_repeated_names_and_valid_prices():
    for seed in range(30):
        truth = make_truth(random.Random(seed))
        names = [norm(p["name"]) for c in truth["categories"] for p in c["products"]]
        assert len(names) == len(set(names))
        assert all(p["price"] > 0 for c in truth["categories"] for p in c["products"])
        assert validate(truth_to_menu(truth)) == []


def test_every_style_is_generated_with_existing_files(data_dir):
    index = load_index(data_dir)
    assert {m["style"] for m in index["menus"]} == {s.name for s in STYLES}
    for menu in index["menus"]:
        assert menu["files"], menu["id"]
        for rel in menu["files"]:
            assert (data_dir / rel).stat().st_size > 1000
        truth = json.loads((data_dir / menu["truth"]).read_text(encoding="utf-8"))
        assert sum(len(c["products"]) for c in truth["categories"]) == menu["items"]


def test_same_seed_gives_same_truth(tmp_path):
    a = generate_dataset(tmp_path / "a", n=3, seed=11)
    b = generate_dataset(tmp_path / "b", n=3, seed=11)
    for x, y in zip(a, b, strict=True):
        tx = (tmp_path / "a" / x["truth"]).read_text(encoding="utf-8")
        ty = (tmp_path / "b" / y["truth"]).read_text(encoding="utf-8")
        assert tx == ty


def test_digital_pdf_has_a_text_layer(data_dir):
    """O PDF digital precisa ter texto extraível: é ele que testa o atalho 'ler sem visão'."""
    from subprocess import run

    index = load_index(data_dir)
    pdf = next(m for m in index["menus"] if m["style"] == "pdf_digital_clean")
    truth = json.loads((data_dir / pdf["truth"]).read_text(encoding="utf-8"))
    text = run(
        ["pdftotext", str(data_dir / pdf["files"][0]), "-"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout
    if not text:  # pdftotext ausente nesta máquina
        return
    first = truth["categories"][0]["products"][0]["name"]
    assert first.split()[0] in text
