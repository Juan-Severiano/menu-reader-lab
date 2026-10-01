# menu-reader-lab

Laboratório para medir **qualidade, custo e latência** de leitores de cardápio por IA, na nuvem e no computador local, em cardápios sintéticos com gabarito.

A pergunta que guia o projeto: **qual é a leitura mais barata que ainda passa na conferência?** Ler um cardápio a partir de fotos ou PDF é uma tarefa comum em plataformas de delivery e PDV (o lojista envia o cardápio e a IA monta o cadastro). Quase ninguém mede quanto esse leitor acerta e quanto custa, e a escolha de provedor e de modelo costuma ser um palpite.

![Amostras do conjunto sintético: PDF digital, foto, foto com pouca luz, quadro-negro e captura de tela](docs/amostras.jpg)

## Estado

Projeto no **Dia 1**. O que existe e o que não existe:

| | Estado |
|---|---|
| Gerador de cardápios sintéticos com gabarito (10 estilos, PDF e imagem) | feito |
| Avaliador (itens, preço, categoria, itens inventados, JSON válido) | feito e validado com leitores de ruído conhecido |
| Custo em dólar por leitura, com tabela de preços versionada e fonte | feito |
| Teto de gasto obrigatório em leitor pago | feito |
| Leitor da OpenAI (a régua) | escrito, **nunca executado contra a API real** (testado com cliente falso) |
| Leitores da Anthropic e do Gemini | não feito |
| Alavancas de otimização (reduzir imagem, texto do PDF, cache, modelo menor, saída compacta) | não feito |
| Modelos de visão locais, OCR local e cascata | não feito |
| Cardápios reais | não feito (ficam no privado, com autorização de cada lojista) |

**Ainda não há nenhum resultado de modelo real neste repositório.** Os números abaixo são só a validação do avaliador.

## Como funciona

```
gerar cardápios  →  leitor (arquivos → JSON)  →  avaliador (JSON × gabarito)  →  relatório
  com gabarito       oracle · noisy · openai       itens, preço, categoria,        tabela e gráfico
                                                   inventado, custo, latência
```

Todo leitor recebe os arquivos (fotos ou PDF) e devolve o mesmo JSON, no mesmo schema. Assim qualquer leitor é avaliado do mesmo jeito.

```json
{
  "sections": [{"title": "Lanches", "itemCount": 2}],
  "categories": [{"name": "Lanches", "products": [
    {"name": "X-Burger", "description": "Pão, hambúrguer e queijo", "price": 28.0}
  ]}]
}
```

O inventário `sections` (cada seção e quantos itens ela tem) deixa o servidor conferir se o modelo leu tudo, mas gasta tokens de saída. Ele é opcional (`--no-inventory`) justamente para medir quanto custa e quanto ajuda.

## O conjunto sintético

60 cardápios com semente fixa (`--seed 7`), 1.561 itens e 99 arquivos (75 MB, não versionados: o gerador os recria em ~30 s). Cada estilo testa uma dificuldade diferente:

| Estilo | O que testa |
|---|---|
| `pdf_digital_clean`, `pdf_digital_2col` | PDF com **texto digital** (dá para ler sem visão), uma e duas colunas |
| `pdf_scan` | PDF só de imagem, com inclinação e granulação |
| `photo_straight` | foto com perspectiva, rotação e sombra |
| `photo_lowlight` | pouca luz e ruído alto |
| `photo_blur` | desfoque e duas colunas |
| `photo_2col_serif` | fonte com serifa, duas colunas, categoria que continua na outra coluna sem título |
| `chalkboard` | texto claro em fundo escuro, fonte monoespaçada |
| `screenshot_compact` | captura de tela pequena, sem descrições |
| `photo_multipage` | o mesmo cardápio em várias fotos |

Os preços aparecem em formatos diferentes (`R$ 24,90`, `24,90`, `R$24,90`), e as pizzas têm versões por tamanho que viram produtos separados.

## Como o avaliador mede

- **Casamento de itens:** pelo nome, sem acento, caixa ou pontuação, com tolerância a erro de leitura (similaridade ≥ 88 em `token_sort_ratio`). Os pares mais parecidos casam primeiro, então "Pizza Margherita - Média" nunca vira "Pizza Margherita - Grande".
- **Itens inventados:** item lido sem par no gabarito, ou duplicado. `inventado = FP / (TP + FP)`.
- **Itens perdidos:** item do gabarito sem par. Entram na revocação.
- **Preço certo:** entre os itens casados, preço dentro de meio centavo.
- **Categoria certa:** entre os itens casados, categoria parecida (≥ 80).
- **JSON válido:** conformidade com o schema estrito. Um JSON inválido ainda é pontuado, mas conta contra o leitor.
- **Custo:** tokens × preço de `src/menu_reader_lab/pricing.json`. Modelo sem preço na tabela vira "n/d", nunca um valor inventado.

As métricas somam os acertos de todos os cardápios antes de dividir (micro). Dá para ver também por estilo.

## Validação do avaliador

Antes de medir qualquer modelo, o avaliador foi testado com leitores de custo zero, e as notas têm que acompanhar o que foi aplicado:

| Leitor | O que faz | F1 de itens | Revocação | Preço certo | Inventado |
|---|---|---|---|---|---|
| `oracle` | devolve o gabarito | 1,0000 | 1,0000 | 1,0000 | 0,0000 |
| `noisy` 10% | perde 10% dos itens, erra 10% dos preços, renomeia 5%, inventa 5% | 0,8787 | 0,8584 | 0,9037 | 0,1001 |
| `noisy` 30% | perde 30%, erra 30%, renomeia 15%, inventa 15% | 0,6557 | 0,5894 | 0,7076 | 0,2610 |

Com 10% de ruído, a revocação esperada é perto de 0,86 (10% perdidos mais ~5% renomeados) e o inventado perto de 0,10: bate. Os 35 testes automatizados cobrem isso, o gerador, o cálculo de custo, o formato do pedido à OpenAI e o teto de gasto.

## Como usar

Pré-requisito: [uv](https://docs.astral.sh/uv/).

```bash
# 1. gerar o conjunto
uv run menu-lab generate --n 60 --seed 7

# 2. leitores sem custo, para conferir a esteira
uv run menu-lab run --reader oracle --run-id sanity-oracle
uv run menu-lab run --reader noisy --noise 0.1 --run-id sanity-noise-10

# 3. leitor pago (exige chave e teto de gasto)
export OPENAI_API_KEY=...   # nunca grave a chave no código nem no Git
uv run --extra openai menu-lab run --reader openai --model gpt-4.1 --detail high \
    --max-usd 2 --limit 10 --run-id openai-gpt-4.1-high

# 4. relatório
uv run menu-lab report
```

### Teto de gasto

Leitor pago **não roda sem `--max-usd`** e não roda com modelo que não tenha preço na tabela (sem preço não há como impor o teto). O teto é checado **antes** de cada chamada: o gasto acumulado mais o custo médio das leituras anteriores não pode passar do limite. Só a primeira leitura não tem estimativa, então se ela sozinha custar mais que o teto, ele é furado. Comece com `--limit` pequeno.

### Preços

`pricing.json` guarda o preço por milhão de tokens, a data da consulta e o link de cada fonte. Preços mudam (o Gemini tem reajuste agendado para 30/11/2026 e 31/12/2026): reconfira antes de tirar conclusões de custo.

## Limitações

- **Sintético é mais fácil que real.** Fonte limpa, sem sujeira, sem letra de mão, sem foto de cardápio dobrado. Os números daqui são um teto, e o que decide é o conjunto real.
- Só as fontes DejaVu (as que vêm com o matplotlib, para o resultado ser o mesmo em qualquer máquina) e só português do Brasil.
- Ainda não há adicionais (grupos de opções) no schema, só categorias, produtos, descrição e preço.
- O casamento por nome tem limiar fixo. Nomes muito parecidos de verdade podem casar errado, e o teste cobre só o caso das pizzas por tamanho.

## Próximos passos

1. Leitores da Anthropic e do Gemini e a primeira tabela real (régua `gpt-4.1` contra modelos menores).
2. Alavancas: reduzir a foto antes de enviar, texto do PDF digital em vez de visão, cache de prompt, saída compacta, com e sem o inventário.
3. OCR local e modelos de visão leves (Qwen3-VL, SmolVLM2, granite-docling) e a **cascata**: tenta o local e só chama a nuvem quando a conferência falha.
4. Cardápios reais, com autorização, só no privado.

## Licença

[MIT](LICENSE).
