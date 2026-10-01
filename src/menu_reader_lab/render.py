"""Desenho dos cardápios: um motor de layout e dois destinos (imagem e PDF digital).

O layout é calculado uma vez, em pixels, e vira uma lista de comandos de desenho. A imagem usa
Pillow e o PDF digital usa ReportLab, com camada de texto real. As fontes são as DejaVu que vêm
com o matplotlib, então o resultado é o mesmo em qualquer máquina.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from reportlab.lib.colors import HexColor
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

DPI = 200
PAGE_W, PAGE_H = 1654, 2339  # A4 a 200 dpi
MARGIN = 110
GUTTER = 70

_FONT_DIR = Path(matplotlib.get_data_path()) / "fonts" / "ttf"
_FONT_FILES = {
    ("sans", False): "DejaVuSans.ttf",
    ("sans", True): "DejaVuSans-Bold.ttf",
    ("serif", False): "DejaVuSerif.ttf",
    ("serif", True): "DejaVuSerif-Bold.ttf",
    ("mono", False): "DejaVuSansMono.ttf",
    ("mono", True): "DejaVuSansMono-Bold.ttf",
}


@dataclass(frozen=True)
class Style:
    """Aparência de um cardápio. `medium` define o arquivo gerado."""

    name: str
    medium: str  # pdf_digital | pdf_scan | photo | screenshot
    columns: int = 1
    family: str = "sans"
    palette: tuple[str, str, str] = ("#ffffff", "#1d1d1f", "#b3261e")  # fundo, texto, destaque
    descriptions: bool = True
    scale: float = 1.0
    page: tuple[int, int] = (PAGE_W, PAGE_H)
    pages: int = 1  # quantas imagens o cardápio ocupa (fotos de partes diferentes)
    price_format: str = "R$ {v}"
    augment: dict[str, float] = field(default_factory=dict)


STYLES: list[Style] = [
    Style("pdf_digital_clean", "pdf_digital"),
    Style(
        "pdf_digital_2col",
        "pdf_digital",
        columns=2,
        family="serif",
        palette=("#fffaf0", "#2b2118", "#7a4b1e"),
        price_format="{v}",
    ),
    Style(
        "pdf_scan",
        "pdf_scan",
        family="serif",
        palette=("#fdfdfb", "#222222", "#444444"),
        price_format="R${v}",
        augment={"rot": 1.2, "noise": 7.0, "blur": 0.6},
    ),
    Style(
        "photo_straight",
        "photo",
        price_format="R$ {v}",
        augment={"persp": 0.025, "rot": 2.0, "noise": 5.0, "blur": 0.7, "shade": 0.18},
    ),
    Style(
        "photo_lowlight",
        "photo",
        palette=("#f6f1e7", "#1d1d1f", "#8b2c1f"),
        augment={
            "persp": 0.035,
            "rot": 3.0,
            "noise": 14.0,
            "blur": 1.0,
            "shade": 0.35,
            "dim": 0.55,
        },
    ),
    Style(
        "photo_blur",
        "photo",
        columns=2,
        price_format="{v}",
        augment={"persp": 0.03, "rot": 2.5, "noise": 6.0, "blur": 2.0, "shade": 0.2},
    ),
    Style(
        "photo_2col_serif",
        "photo",
        columns=2,
        family="serif",
        palette=("#fff8e7", "#33261a", "#9c3d1e"),
        augment={"persp": 0.04, "rot": 3.5, "noise": 8.0, "blur": 0.8, "shade": 0.25},
    ),
    Style(
        "chalkboard",
        "photo",
        family="mono",
        palette=("#1f2a24", "#f1f1ea", "#e8c547"),
        price_format="R$ {v}",
        augment={"persp": 0.03, "rot": 2.0, "noise": 9.0, "blur": 1.1, "shade": 0.2},
    ),
    Style(
        "screenshot_compact",
        "screenshot",
        descriptions=False,
        scale=0.78,
        page=(1080, 1900),
        price_format="R$ {v}",
    ),
    Style(
        "photo_multipage",
        "photo",
        page=(PAGE_W, 1500),
        pages=2,
        price_format="R$ {v}",
        augment={"persp": 0.03, "rot": 2.0, "noise": 6.0, "blur": 0.8, "shade": 0.2},
    ),
]
STYLE_BY_NAME = {s.name: s for s in STYLES}


@lru_cache(maxsize=None)
def _font(family: str, bold: bool, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(_FONT_DIR / _FONT_FILES[(family, bold)]), size)


@dataclass
class Text:
    x: int
    y: int  # linha de base
    text: str
    family: str
    bold: bool
    size: int
    color: str
    align: str = "l"


@dataclass
class Rect:
    x0: int
    y0: int
    x1: int
    y1: int
    color: str


@dataclass
class Page:
    width: int
    height: int
    bg: str
    rects: list[Rect] = field(default_factory=list)
    texts: list[Text] = field(default_factory=list)


def _price_text(value: float, style: Style) -> str:
    comma = f"{value:.2f}".replace(".", ",")
    return style.price_format.format(v=comma)


def _wrap(text: str, family: str, bold: bool, size: int, width: int) -> list[str]:
    fnt = _font(family, bold, size)
    lines: list[str] = []
    current = ""
    for word in text.split():
        trial = f"{current} {word}".strip()
        if fnt.getlength(trial) <= width or not current:
            current = trial
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def layout(truth: dict[str, Any], style: Style, restaurant: str) -> list[Page]:
    """Posiciona título, categorias, itens, preços e descrições, paginando quando precisa."""
    w, h = style.page
    bg, fg, accent = style.palette
    s = style.scale
    size_title, size_cat = int(78 * s), int(44 * s)
    size_item, size_desc = int(34 * s), int(26 * s)
    muted = "#6b6b6b" if bg != "#1f2a24" else "#b9b9b0"

    pages = [Page(w, h, bg)]
    col_w = (w - 2 * MARGIN - GUTTER * (style.columns - 1)) // style.columns
    state = {"col": 0, "y": MARGIN, "first_y": MARGIN}

    def page() -> Page:
        return pages[-1]

    def col_x() -> int:
        return MARGIN + state["col"] * (col_w + GUTTER)

    def ensure(height: int) -> None:
        if state["y"] + height <= h - MARGIN:
            return
        state["col"] += 1
        # Na primeira página as colunas começam abaixo do título.
        state["y"] = state["first_y"] if len(pages) == 1 else MARGIN
        if state["col"] >= style.columns:
            pages.append(Page(w, h, bg))
            state["col"] = 0
            state["y"] = MARGIN

    page().texts.append(
        Text(w // 2, MARGIN + size_title, restaurant, style.family, True, size_title, fg, "c")
    )
    page().texts.append(
        Text(
            w // 2,
            MARGIN + size_title + int(54 * s),
            "CARDÁPIO",
            style.family,
            True,
            int(30 * s),
            accent,
            "c",
        )
    )
    page().rects.append(
        Rect(
            w // 2 - 120,
            MARGIN + size_title + int(76 * s),
            w // 2 + 120,
            MARGIN + size_title + int(82 * s),
            accent,
        )
    )
    state["y"] = MARGIN + size_title + int(150 * s)
    state["first_y"] = state["y"]

    for cat in truth["categories"]:
        bar_h = int(size_cat * 1.7)
        ensure(bar_h + int(size_item * 3))
        x, y = col_x(), state["y"]
        page().rects.append(Rect(x, y, x + col_w, y + bar_h, accent))
        label_color = "#ffffff" if accent != "#e8c547" else "#1f2a24"
        page().texts.append(
            Text(
                x + 24,
                y + int(bar_h * 0.68),
                cat["name"].upper(),
                style.family,
                True,
                size_cat,
                label_color,
            )
        )
        state["y"] = y + bar_h + int(size_item * 0.9)

        for product in cat["products"]:
            price = _price_text(product["price"], style) if product["price"] is not None else ""
            price_w = _font(style.family, True, size_item).getlength(price) if price else 0
            name_lines = _wrap(
                product["name"], style.family, True, size_item, int(col_w - price_w - 40)
            )
            desc_lines = (
                _wrap(product["description"], style.family, False, size_desc, col_w)
                if style.descriptions and product.get("description")
                else []
            )
            height = (
                int(size_item * 1.35) * len(name_lines)
                + int(size_desc * 1.3) * len(desc_lines)
                + int(size_item * 0.7)
            )
            ensure(height)
            x, y = col_x(), state["y"]
            baseline = y + size_item
            for i, line in enumerate(name_lines):
                page().texts.append(
                    Text(
                        x,
                        baseline + i * int(size_item * 1.35),
                        line,
                        style.family,
                        True,
                        size_item,
                        fg,
                    )
                )
            if price:
                page().texts.append(
                    Text(x + col_w, baseline, price, style.family, True, size_item, accent, "r")
                )
                first_w = _font(style.family, True, size_item).getlength(name_lines[0])
                dot_w = _font(style.family, False, size_desc).getlength(".")
                room = col_w - first_w - price_w - 60
                if len(name_lines) == 1 and room > dot_w * 4:
                    dots = "." * int(room // dot_w)
                    page().texts.append(
                        Text(
                            x + int(first_w) + 20,
                            baseline,
                            dots,
                            style.family,
                            False,
                            size_desc,
                            muted,
                        )
                    )
            cursor = baseline + (len(name_lines) - 1) * int(size_item * 1.35)
            for line in desc_lines:
                cursor += int(size_desc * 1.3)
                page().texts.append(Text(x, cursor, line, style.family, False, size_desc, muted))
            state["y"] = y + height
        state["y"] += int(size_item * 0.6)
    return pages


def to_image(pg: Page) -> Image.Image:
    img = Image.new("RGB", (pg.width, pg.height), pg.bg)
    draw = ImageDraw.Draw(img)
    for r in pg.rects:
        draw.rectangle([r.x0, r.y0, r.x1, r.y1], fill=r.color)
    for t in pg.texts:
        anchor = {"l": "ls", "r": "rs", "c": "ms"}[t.align]
        draw.text(
            (t.x, t.y), t.text, font=_font(t.family, t.bold, t.size), fill=t.color, anchor=anchor
        )
    return img


def to_pdf(pages: list[Page], path: Path) -> None:
    """PDF com camada de texto real (o que `pypdf` ou `pdftotext` conseguem extrair)."""
    scale = 72 / DPI
    names: dict[tuple[str, bool], str] = {}
    for key, file in _FONT_FILES.items():
        name = f"{key[0]}{'B' if key[1] else 'R'}"
        if name not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(name, str(_FONT_DIR / file)))
        names[key] = name
    first = pages[0]
    c = canvas.Canvas(str(path), pagesize=(first.width * scale, first.height * scale))
    for pg in pages:
        c.setPageSize((pg.width * scale, pg.height * scale))
        c.setFillColor(HexColor(pg.bg))
        c.rect(0, 0, pg.width * scale, pg.height * scale, fill=1, stroke=0)
        for r in pg.rects:
            c.setFillColor(HexColor(r.color))
            c.rect(
                r.x0 * scale,
                (pg.height - r.y1) * scale,
                (r.x1 - r.x0) * scale,
                (r.y1 - r.y0) * scale,
                fill=1,
                stroke=0,
            )
        for t in pg.texts:
            c.setFillColor(HexColor(t.color))
            c.setFont(names[(t.family, t.bold)], t.size * scale)
            x, y = t.x * scale, (pg.height - t.y) * scale
            if t.align == "r":
                c.drawRightString(x, y, t.text)
            elif t.align == "c":
                c.drawCentredString(x, y, t.text)
            else:
                c.drawString(x, y, t.text)
        c.showPage()
    c.save()


def _perspective_coeffs(dst: list[tuple[float, float]], src: list[tuple[float, float]]):
    rows = []
    for (x, y), (u, v) in zip(dst, src, strict=True):
        rows.append([x, y, 1, 0, 0, 0, -u * x, -u * y])
        rows.append([0, 0, 0, x, y, 1, -v * x, -v * y])
    return np.linalg.solve(np.array(rows, dtype=float), np.array(src, dtype=float).reshape(8))


def augment_photo(
    img: Image.Image, rng: random.Random, np_rng: np.random.Generator, params: dict[str, float]
) -> Image.Image:
    """Simula a foto de um cardápio sobre uma mesa: perspectiva, rotação, luz, foco e ruído."""
    w, h = img.size
    pad = 0.07
    bw, bh = int(w * (1 + 2 * pad)), int(h * (1 + 2 * pad))
    base = np.array(rng.choice([(96, 74, 56), (120, 120, 118), (52, 52, 56), (160, 142, 120)]))
    table = np.clip(
        base + np_rng.normal(0, 9, (bh, bw, 1)) + np_rng.normal(0, 4, (bh, bw, 3)), 0, 255
    ).astype(np.uint8)
    canvas_img = Image.fromarray(table, "RGB").convert("RGBA")

    persp = params.get("persp", 0.0)
    ox, oy = int(w * pad), int(h * pad)
    jitter = lambda: rng.uniform(-persp, persp)  # noqa: E731
    corners = [(ox, oy), (ox + w, oy), (ox + w, oy + h), (ox, oy + h)]
    dst = [(x + jitter() * w, y + jitter() * h) for x, y in corners]
    rot = np.deg2rad(rng.uniform(-params.get("rot", 0.0), params.get("rot", 0.0)))
    cx, cy = ox + w / 2, oy + h / 2
    dst = [
        (
            cx + (x - cx) * np.cos(rot) - (y - cy) * np.sin(rot),
            cy + (x - cx) * np.sin(rot) + (y - cy) * np.cos(rot),
        )
        for x, y in dst
    ]
    coeffs = _perspective_coeffs(dst, [(0, 0), (w, 0), (w, h), (0, h)])
    page_rgba = img.convert("RGBA").transform((bw, bh), Image.PERSPECTIVE, coeffs, Image.BICUBIC)
    canvas_img.alpha_composite(page_rgba)

    arr = np.asarray(canvas_img.convert("RGB"), dtype=np.float32)
    shade = params.get("shade", 0.0)
    if shade:
        angle = rng.uniform(0, 2 * np.pi)
        yy, xx = np.mgrid[0:bh, 0:bw]
        ramp = (xx / bw) * np.cos(angle) + (yy / bh) * np.sin(angle)
        ramp = (ramp - ramp.min()) / (ramp.max() - ramp.min())
        arr *= (1 - shade * ramp)[..., None]
    arr *= params.get("dim", 1.0)
    out = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB")
    if params.get("blur"):
        out = out.filter(ImageFilter.GaussianBlur(params["blur"]))
    noise = params.get("noise", 0.0)
    if noise:
        arr = np.asarray(out, dtype=np.float32) + np_rng.normal(0, noise, (bh, bw, 1))
        out = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB")
    return out


def augment_scan(
    img: Image.Image, rng: random.Random, np_rng: np.random.Generator, params: dict[str, float]
) -> Image.Image:
    """Escaneamento: pequena inclinação, desfoque leve e granulação, sem fundo de mesa."""
    out = img.rotate(
        rng.uniform(-params.get("rot", 0), params.get("rot", 0)),
        resample=Image.BICUBIC,
        fillcolor=(250, 250, 248),
    )
    if params.get("blur"):
        out = out.filter(ImageFilter.GaussianBlur(params["blur"]))
    arr = np.asarray(out, dtype=np.float32) + np_rng.normal(
        0, params.get("noise", 0), out.size[::-1] + (1,)
    )
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB")


def render_menu(
    truth: dict[str, Any], style: Style, restaurant: str, out_dir: Path, seed: int
) -> list[Path]:
    """Gera os arquivos do cardápio em `out_dir` e devolve os caminhos, na ordem de leitura."""
    rng = random.Random(seed)
    np_rng = np.random.default_rng(seed)
    pages = layout(truth, style, restaurant)
    if style.medium == "pdf_digital":
        path = out_dir / "menu.pdf"
        to_pdf(pages, path)
        return [path]
    images = [to_image(p) for p in pages]
    if style.medium == "pdf_scan":
        scans = [augment_scan(i, rng, np_rng, style.augment) for i in images]
        path = out_dir / "menu.pdf"
        scans[0].save(path, "PDF", resolution=DPI, save_all=True, append_images=scans[1:])
        return [path]
    paths = []
    for index, img in enumerate(images, start=1):
        if style.medium == "photo":
            img = augment_photo(img, rng, np_rng, style.augment)
            path = out_dir / f"menu-{index}.jpg"
            img.save(path, "JPEG", quality=82)
        else:
            path = out_dir / f"menu-{index}.png"
            img.save(path, "PNG")
        paths.append(path)
    return paths
