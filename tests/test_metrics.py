import copy

from menu_reader_lab.metrics import aggregate, norm, score, to_price
from menu_reader_lab.schema import truth_to_menu

TRUTH = {
    "categories": [
        {
            "name": "Lanches",
            "products": [
                {"name": "X-Burger", "description": None, "price": 28.0},
                {"name": "X-Salada", "description": "alface", "price": 26.5},
                {"name": "Misto Quente", "description": None, "price": 12.9},
            ],
        },
        {
            "name": "Bebidas",
            "products": [
                {"name": "Água Mineral", "description": None, "price": 4.0},
                {"name": "Suco de Laranja", "description": None, "price": 9.9},
            ],
        },
    ]
}


def perfect():
    return truth_to_menu(TRUTH)


def test_norm_ignores_accents_case_and_punctuation():
    assert norm("  ÁGUA, Mineral! ") == "agua mineral"
    assert norm("X-Burger") == "x burger"


def test_to_price_accepts_numbers_and_brazilian_text():
    assert to_price(12.9) == 12.9
    assert to_price("R$ 12,90") == 12.9
    assert to_price("R$ 1.234,56") == 1234.56
    assert to_price("12.90") == 12.9
    assert to_price("grátis") is None
    assert to_price(True) is None
    assert to_price(None) is None


def test_perfect_reading_scores_everything():
    s = score(TRUTH, perfect())
    assert (s.tp, s.fp, s.fn) == (5, 0, 0)
    assert s.price_ok == s.price_total == 5
    assert s.category_ok == s.category_total == 5
    assert s.json_valid and s.exact


def test_accent_and_case_differences_still_match():
    pred = perfect()
    pred["categories"][1]["products"][0]["name"] = "AGUA MINERAL"
    s = score(TRUTH, pred)
    assert s.tp == 5 and s.fp == 0


def test_missing_item_is_a_false_negative():
    pred = perfect()
    pred["categories"][0]["products"].pop()
    pred["sections"][0]["itemCount"] = 2
    s = score(TRUTH, pred)
    assert (s.tp, s.fp, s.fn) == (4, 0, 1)
    assert not s.exact


def test_invented_and_duplicated_items_are_false_positives():
    pred = perfect()
    pred["categories"][0]["products"].append(
        {"name": "Pizza Gigante da Casa", "description": None, "price": 50.0}
    )
    pred["categories"][0]["products"].append(copy.deepcopy(pred["categories"][0]["products"][0]))
    s = score(TRUTH, pred)
    assert (s.tp, s.fp, s.fn) == (5, 2, 0)
    assert aggregate([s])["hallucination_rate"] == round(2 / 7, 4)


def test_wrong_price_is_counted_only_in_price_accuracy():
    pred = perfect()
    pred["categories"][0]["products"][0]["price"] = 29.0
    s = score(TRUTH, pred)
    assert s.tp == 5 and s.price_ok == 4 and s.price_total == 5
    assert not s.exact


def test_item_under_the_wrong_category_hurts_category_accuracy():
    pred = perfect()
    item = pred["categories"][0]["products"].pop()
    pred["sections"][0]["itemCount"] = 2
    pred["categories"][1]["products"].append(item)
    pred["sections"][1]["itemCount"] = 3
    s = score(TRUTH, pred)
    assert s.tp == 5 and s.category_ok == 4


def test_pizza_sizes_are_not_confused():
    truth = {
        "categories": [
            {
                "name": "Pizzas",
                "products": [
                    {"name": "Pizza Margherita - Média", "description": None, "price": 40.0},
                    {"name": "Pizza Margherita - Grande", "description": None, "price": 52.0},
                ],
            }
        ]
    }
    s = score(truth, truth_to_menu(truth))
    assert (s.tp, s.fp, s.fn) == (2, 0, 0) and s.price_ok == 2


def test_no_response_loses_every_item():
    s = score(TRUTH, None)
    assert (s.tp, s.fp, s.fn) == (0, 0, 5) and not s.json_valid


def test_schema_violation_is_flagged_but_still_scored():
    pred = perfect()
    del pred["sections"]
    s = score(TRUTH, pred)
    assert not s.json_valid and s.schema_errors and s.tp == 5


def test_aggregate_sums_before_dividing():
    full, empty = score(TRUTH, perfect()), score(TRUTH, None)
    agg = aggregate([full, empty])
    assert agg["item_recall"] == 0.5 and agg["item_precision"] == 1.0
    assert agg["json_valid_rate"] == 0.5
