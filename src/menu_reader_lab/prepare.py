"""Preparo dos arquivos antes de enviar ao modelo: alavancas que não dependem do provedor.

- `shrink_image` reduz a foto (nunca amplia) e a regrava em JPEG, para pagar menos tokens de imagem.
- `pdf_text` extrai o texto de um PDF digital com `pypdf` (BSD-3), para mandar só texto. PDF sem
  camada de texto (escaneado) devolve `None` e segue como arquivo, para o modelo enxergar.

O quanto cada uma custa em qualidade só se sabe lendo com um modelo e comparando com o gabarito.
"""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image
from pypdf import PdfReader

# Abaixo disso o PDF não tem camada de texto útil (escaneado, ou só um rodapé).
MIN_TEXT_CHARS = 200


def shrink_image(path: Path, max_side: int, quality: int = 85) -> tuple[bytes, str]:
    """Bytes e tipo da imagem com o lado maior em no máximo `max_side` px.

    Imagem que já cabe é devolvida sem mexer, sem recomprimir.
    """
    if max_side <= 0:
        raise ValueError("max_side precisa ser positivo")
    with Image.open(path) as img:
        if max(img.size) <= max_side:
            return path.read_bytes(), _mime(path)
        scale = max_side / max(img.size)
        size = (max(1, round(img.width * scale)), max(1, round(img.height * scale)))
        small = img.convert("RGB").resize(size, Image.Resampling.LANCZOS)
    out = io.BytesIO()
    small.save(out, format="JPEG", quality=quality, optimize=True)
    return out.getvalue(), "image/jpeg"


def _mime(path: Path) -> str:
    return {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
    }[path.suffix.lower()]


def pdf_text(path: Path, min_chars: int = MIN_TEXT_CHARS) -> str | None:
    """Texto do PDF, página por página, ou `None` se não houver texto útil.

    Usa a extração padrão do `pypdf` (na ordem do fluxo de conteúdo). Nos PDFs sintéticos de duas
    colunas ela manteve 276 de 276 nomes de item inteiros, contra 262 no modo `layout`, que
    cola o fim de uma coluna ao começo da outra. PDFs de outras origens podem ordenar diferente.
    """
    reader = PdfReader(str(path))
    pages = [(page.extract_text() or "").rstrip() for page in reader.pages]
    text = "\n\n".join(f"[página {i}]\n{p}" for i, p in enumerate(pages, 1) if p.strip())
    useful = sum(1 for ch in text if ch.isalnum())
    return text if useful >= min_chars else None
