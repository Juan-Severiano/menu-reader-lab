"""Contrato de saída dos leitores e as instruções de leitura.

A forma (`categories[].products[]` e o inventário `sections`) acompanha a de leitores de cardápio
já usados em produto, para que o que for medido aqui encaixe neles depois. O texto das instruções
é próprio deste repositório.
"""

from __future__ import annotations

from typing import Any

from jsonschema import Draft202012Validator

_STR = {"type": "string"}
_NULL_STR = {"type": ["string", "null"]}


def build_schema(inventory: bool = True) -> dict[str, Any]:
    """JSON Schema estrito (todos os campos obrigatórios, nulos explícitos).

    Com `inventory`, o modelo lista as seções e quantos itens cada uma tem antes dos produtos.
    Isso ajuda o servidor a conferir a leitura, mas gasta tokens de saída: é uma das alavancas
    que o laboratório mede.
    """
    product = {
        "type": "object",
        "additionalProperties": False,
        "required": ["name", "description", "price"],
        "properties": {
            "name": _STR,
            "description": _NULL_STR,
            "price": {"type": ["number", "null"]},
        },
    }
    category = {
        "type": "object",
        "additionalProperties": False,
        "required": ["name", "products"],
        "properties": {"name": _STR, "products": {"type": "array", "items": product}},
    }
    properties: dict[str, Any] = {"categories": {"type": "array", "items": category}}
    required = ["categories"]
    if inventory:
        section = {
            "type": "object",
            "additionalProperties": False,
            "required": ["title", "itemCount"],
            "properties": {"title": _STR, "itemCount": {"type": "integer"}},
        }
        properties = {"sections": {"type": "array", "items": section}, **properties}
        required = ["sections", *required]
    return {
        "type": "object",
        "additionalProperties": False,
        "required": required,
        "properties": properties,
    }


def validate(menu: Any, inventory: bool = True) -> list[str]:
    """Erros de conformidade com o schema (lista vazia quando o JSON é válido)."""
    validator = Draft202012Validator(build_schema(inventory))
    return [
        f"{'/'.join(str(p) for p in err.absolute_path) or '<raiz>'}: {err.message}"
        for err in validator.iter_errors(menu)
    ]


def truth_to_menu(truth: dict[str, Any], inventory: bool = True) -> dict[str, Any]:
    """Gabarito no formato exato que um leitor perfeito devolveria."""
    categories = [
        {
            "name": cat["name"],
            "products": [
                {"name": p["name"], "description": p.get("description"), "price": p.get("price")}
                for p in cat["products"]
            ],
        }
        for cat in truth["categories"]
    ]
    menu: dict[str, Any] = {"categories": categories}
    if inventory:
        menu = {
            "sections": [{"title": c["name"], "itemCount": len(c["products"])} for c in categories],
            **menu,
        }
    return menu


SYSTEM_INSTRUCTIONS = """\
Você lê cardápios de restaurantes brasileiros a partir de fotos ou PDF e devolve um JSON.

Regras:
1. Extraia só o que está escrito. Nunca invente, complete ou sugira itens, preços ou descrições.
2. Cada seção do cardápio vira uma categoria, com o nome como está escrito.
3. O preço é um número em reais (12,90 vira 12.9). Se estiver ilegível ou ausente, use null.
4. A descrição só entra se estiver no material. Sem descrição, use null.
5. Versões ou tamanhos com preços diferentes são produtos separados, com o tamanho no nome.
6. Se uma parte estiver ilegível, deixe-a de fora em vez de adivinhar.\
"""

INVENTORY_RULE = (
    "Antes dos produtos, liste em `sections` cada seção do cardápio e quantos itens vendáveis "
    "ela tem. Depois extraia os produtos e confira se a contagem de cada seção bate."
)


def request_text(inventory: bool = True) -> str:
    """Pedido que acompanha as imagens ou o PDF."""
    base = "Leia o cardápio em anexo e devolva o JSON no formato pedido."
    return f"{base} {INVENTORY_RULE}" if inventory else base
