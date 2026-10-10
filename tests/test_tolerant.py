import copy
import json

from menu_reader_lab.metrics import score
from menu_reader_lab.readers.oracle import NoisyReader, OracleReader
from menu_reader_lab.runner import rescore, run

TRUTH = {
    "categories": [
        {
            "name": "Bebidas",
            "products": [
                {"name": "Água Mineral", "description": "500 ml", "price": 4.0},
                {"name": "Suco de Laranja", "description": "Natural, 400 ml", "price": 9.9},
                {"name": "Coca-Cola Lata", "description": None, "price": 6.0},
            ],
        }
    ]
}


def with_names(*names):
    menu = copy.deepcopy(TRUTH)
    for product, name in zip(menu["categories"][0]["products"], names, strict=True):
        product["name"] = name
    return menu


def test_descriptor_in_the_name_is_wrong_for_strict_and_right_for_tolerant():
    read = with_names("Água Mineral 500 ml", "Suco de Laranja Natural 400 ml", "Coca-Cola Lata")
    strict = score(TRUTH, read, inventory=False)
    tolerant = score(TRUTH, read, inventory=False, tolerant=True)
    assert (strict.tp, strict.fp, strict.fn) == (1, 2, 2)
    assert (tolerant.tp, tolerant.fp, tolerant.fn) == (3, 0, 0)


def test_tolerant_does_not_accept_an_unrelated_name():
    read = with_names("Cerveja Long Neck", "Suco de Laranja", "Coca-Cola Lata")
    tolerant = score(TRUTH, read, inventory=False, tolerant=True)
    assert (tolerant.tp, tolerant.fp, tolerant.fn) == (2, 1, 1)


def test_tolerant_never_scores_below_strict():
    read = with_names("Agua Mineral", "Suco Laranja", "Coca Cola")
    strict = score(TRUTH, read, inventory=False)
    tolerant = score(TRUTH, read, inventory=False, tolerant=True)
    assert tolerant.tp >= strict.tp


def test_rescore_rebuilds_the_scores_without_the_api(data_dir, tmp_path):
    run(NoisyReader(drop=0.2, price_error=0.2, rename=0.1, invent=0.1), data_dir, "r", tmp_path)
    path = tmp_path / "r" / "summary.json"
    before = json.loads(path.read_text(encoding="utf-8"))
    after = rescore(tmp_path / "r", data_dir)
    assert after["overall"] == before["overall"]
    assert after["overall_tolerant"]["item_f1"] >= after["overall"]["item_f1"]
    assert after["cost_per_menu_usd"] == before["cost_per_menu_usd"]
    first = json.loads((tmp_path / "r" / "menus.jsonl").read_text().splitlines()[0])
    assert "score_tolerant" in first


def test_oracle_is_perfect_in_both_modes(data_dir, tmp_path):
    summary = run(OracleReader(), data_dir, "o", tmp_path)
    assert summary["overall"]["item_f1"] == summary["overall_tolerant"]["item_f1"] == 1.0
