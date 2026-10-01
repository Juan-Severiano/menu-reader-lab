"""Vocabulário de cardápios brasileiros usado pelo gerador.

Cada categoria tem itens (nome, descrição) e uma faixa de preço em reais. Os nomes têm acentos de
propósito: a leitura de texto acentuado é parte do que o laboratório mede.
"""

from __future__ import annotations

# categoria -> (faixa de preço, [(nome, descrição ou None), ...])
CATEGORIES: dict[str, tuple[tuple[float, float], list[tuple[str, str | None]]]] = {
    "Lanches": (
        (18.0, 39.0),
        [
            ("X-Burger", "Pão, hambúrguer de 160 g, queijo e maionese da casa"),
            ("X-Salada", "Hambúrguer, queijo, alface, tomate e maionese"),
            ("X-Bacon", "Hambúrguer, queijo, bacon crocante e molho barbecue"),
            ("X-Tudo", "Hambúrguer, ovo, presunto, queijo, bacon, alface e tomate"),
            ("X-Frango", "Filé de frango grelhado, queijo, alface e tomate"),
            ("X-Calabresa", "Calabresa fatiada, queijo, cebola e vinagrete"),
            ("Cheddar Melt", "Hambúrguer, cheddar cremoso e cebola caramelizada"),
            ("Hambúrguer Duplo", "Dois hambúrgueres de 120 g, queijo prato e picles"),
            ("Smash Burger", "Dois discos prensados, cheddar e molho especial"),
            ("Sanduíche Natural", "Peito de peru, queijo branco, cenoura e alface"),
            ("Misto Quente", None),
            ("Beirute de Frango", "Pão sírio, frango desfiado, queijo, tomate e orégano"),
        ],
    ),
    "Pizzas": (
        (36.0, 74.0),
        [
            ("Pizza Margherita", "Molho de tomate, mussarela, tomate e manjericão"),
            ("Pizza Calabresa", "Calabresa fatiada, cebola e azeitonas"),
            ("Pizza Portuguesa", "Presunto, ovos, cebola, ervilha e azeitonas"),
            ("Pizza Frango com Catupiry", "Frango desfiado e catupiry original"),
            ("Pizza Quatro Queijos", "Mussarela, provolone, gorgonzola e parmesão"),
            ("Pizza Pepperoni", "Pepperoni fatiado e mussarela"),
            ("Pizza Napolitana", "Mussarela, tomate fatiado e parmesão"),
            ("Pizza Lombo Canadense", "Lombo canadense, mussarela e cebola roxa"),
            ("Pizza de Chocolate", "Chocolate ao leite e granulado"),
            ("Pizza Brigadeiro", None),
        ],
    ),
    "Porções": (
        (26.0, 79.0),
        [
            ("Batata Frita", "Porção de 400 g com sal e orégano"),
            ("Calabresa Acebolada", None),
            ("Frango à Passarinho", "Frango frito temperado com alho"),
            ("Mandioca Frita", None),
            ("Isca de Peixe", "Tilápia empanada com molho tártaro"),
            ("Anéis de Cebola", "Empanados e crocantes"),
            ("Pastel Sortido (6 un.)", "Carne, queijo e frango"),
            ("Bolinho de Bacalhau (8 un.)", None),
            ("Torresmo", "Pururuca crocante com limão"),
            ("Mix de Petiscos", "Batata, calabresa, frango e mandioca"),
        ],
    ),
    "Pratos Executivos": (
        (24.0, 49.0),
        [
            ("Filé de Frango Grelhado", "Arroz, feijão, salada e batata frita"),
            ("Feijoada Completa", "Arroz, couve, farofa, torresmo e laranja"),
            ("Strogonoff de Carne", "Arroz branco e batata palha"),
            ("Parmegiana de Frango", "Arroz, fritas e queijo gratinado"),
            ("Picanha na Chapa", "Arroz, feijão tropeiro e vinagrete"),
            ("Peixe Frito", "Tilápia inteira, arroz, pirão e salada"),
            ("Baião de Dois", "Arroz, feijão-de-corda, queijo coalho e carne de sol"),
            ("Macarronada à Bolonhesa", None),
            ("Bife Acebolado", "Arroz, feijão, ovo e batata frita"),
            ("Galinhada", "Arroz com frango, milho e cheiro-verde"),
        ],
    ),
    "Saladas": (
        (18.0, 33.0),
        [
            ("Salada Caesar", "Alface americana, frango, croutons e parmesão"),
            ("Salada Caprese", "Tomate, mussarela de búfala e manjericão"),
            ("Salada Tropical", "Folhas verdes, manga, castanhas e molho de mel"),
            ("Salada Grega", "Pepino, tomate, azeitona, queijo feta e orégano"),
            ("Salpicão", "Frango desfiado, maçã, passas e maionese"),
            ("Salada de Grão-de-Bico", None),
        ],
    ),
    "Bebidas": (
        (4.0, 22.0),
        [
            ("Coca-Cola Lata", "350 ml"),
            ("Guaraná Antarctica Lata", "350 ml"),
            ("Suco de Laranja", "Natural, 400 ml"),
            ("Suco de Abacaxi com Hortelã", "Natural, 400 ml"),
            ("Água Mineral", "500 ml"),
            ("Água com Gás", "500 ml"),
            ("Cerveja Long Neck", None),
            ("Chá Gelado de Pêssego", None),
            ("Café Expresso", None),
            ("Limonada Suíça", "Limão, leite condensado e gelo"),
            ("Vitamina de Banana", "Leite, banana e aveia"),
        ],
    ),
    "Sobremesas": (
        (9.0, 27.0),
        [
            ("Pudim de Leite", "Fatia com calda de caramelo"),
            ("Mousse de Maracujá", None),
            ("Brownie com Sorvete", "Brownie quente e sorvete de creme"),
            ("Petit Gâteau", "Bolinho de chocolate com recheio cremoso"),
            ("Torta de Limão", "Fatia com merengue maçaricado"),
            ("Bolo de Rolo", None),
            ("Sorvete (2 bolas)", "Creme, chocolate ou morango"),
            ("Cartola", "Banana frita, queijo coalho, açúcar e canela"),
        ],
    ),
    "Açaí": (
        (14.0, 34.0),
        [
            ("Açaí 300 ml", "Com banana e granola"),
            ("Açaí 500 ml", "Com banana e granola"),
            ("Açaí 700 ml", "Com banana e granola"),
            ("Tigela Tropical", "Açaí, manga, kiwi, coco ralado e mel"),
            ("Açaí com Leite Ninho", "Açaí, leite em pó e leite condensado"),
            ("Barca de Açaí", "1 litro, com 4 acompanhamentos à escolha"),
            ("Açaí Fit", None),
        ],
    ),
    "Café da Manhã": (
        (6.0, 24.0),
        [
            ("Pão na Chapa", "Com manteiga"),
            ("Tapioca de Queijo", "Goma de tapioca e queijo coalho"),
            ("Cuscuz com Ovo", None),
            ("Omelete Simples", "Dois ovos, queijo e orégano"),
            ("Pão de Queijo (5 un.)", None),
            ("Bolo Caseiro", "Fatia, sabor do dia"),
            ("Misto Quente", None),
        ],
    ),
}

RESTAURANTS = [
    "Cantina do Zé",
    "Lanchonete Maré Mansa",
    "Pizzaria Forno Antigo",
    "Açaí do Litoral",
    "Bar do Seu Chico",
    "Sabor da Vila",
    "Cozinha da Dona Lúcia",
    "Burger Beira-Mar",
    "Empório do Sertão",
    "Doce Esquina",
]

# Pizzas e açaís têm versões de preço diferente: viram produtos separados, com o tamanho no nome.
PIZZA_SIZES = [("Média", 0.0), ("Grande", 12.0)]
