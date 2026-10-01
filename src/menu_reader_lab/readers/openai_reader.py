"""Leitor da OpenAI (Responses API): a régua, equivalente ao leitor em uso em produto.

Uma chamada por cardápio, imagens em base64 com `detail` configurável, PDF como arquivo e saída
em JSON Schema estrito. **Não foi testado contra a API real** (precisa de chave e de um teto de
gasto definido por quem roda): os testes usam um cliente falso e conferem o formato do pedido e
da resposta.
"""

from __future__ import annotations

import base64
import json
import os
import time
from pathlib import Path
from typing import Any

from ..schema import SYSTEM_INSTRUCTIONS, build_schema, request_text
from .base import ReadResult, Usage

_IMAGE_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}


class OpenAIReader:
    name = "openai"
    paid = True

    def __init__(
        self,
        model: str = "gpt-4.1",
        detail: str = "high",
        inventory: bool = True,
        max_output_tokens: int = 16000,
        client: Any = None,
    ) -> None:
        self.model = model
        self.detail = detail
        self.inventory = inventory
        self.max_output_tokens = max_output_tokens
        if client is None:
            try:
                from openai import OpenAI
            except ImportError as exc:  # pragma: no cover
                raise RuntimeError(
                    "Instale o extra: pip install 'menu-reader-lab[openai]'"
                ) from exc
            if not os.environ.get("OPENAI_API_KEY"):
                raise RuntimeError(
                    "Defina OPENAI_API_KEY no ambiente (nunca grave a chave no código nem no Git)."
                )
            client = OpenAI()  # lê OPENAI_API_KEY do ambiente
        self.client = client

    def _content(self, files: list[Path]) -> list[dict[str, Any]]:
        content: list[dict[str, Any]] = [
            {"type": "input_text", "text": request_text(self.inventory)}
        ]
        for path in files:
            data = base64.b64encode(path.read_bytes()).decode("ascii")
            if path.suffix.lower() == ".pdf":
                content.append(
                    {
                        "type": "input_file",
                        "filename": path.name,
                        "file_data": f"data:application/pdf;base64,{data}",
                    }
                )
            else:
                mime = _IMAGE_TYPES[path.suffix.lower()]
                content.append(
                    {
                        "type": "input_image",
                        "detail": self.detail,
                        "image_url": f"data:{mime};base64,{data}",
                    }
                )
        return content

    def read(self, files: list[Path]) -> ReadResult:
        started = time.perf_counter()
        try:
            response = self.client.responses.create(
                model=self.model,
                instructions=SYSTEM_INSTRUCTIONS,
                input=[{"role": "user", "content": self._content(files)}],
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "cardapio",
                        "strict": True,
                        "schema": build_schema(self.inventory),
                    }
                },
                max_output_tokens=self.max_output_tokens,
                store=False,
            )
        except Exception as exc:  # a API pode falhar de muitas formas; o erro vira dado
            return ReadResult(
                menu=None,
                model=self.model,
                latency_s=time.perf_counter() - started,
                error=f"{type(exc).__name__}: {str(exc)[:200]}",
            )
        latency = time.perf_counter() - started
        raw = getattr(response, "usage", None)
        details = getattr(raw, "input_tokens_details", None)
        usage = Usage(
            input_tokens=int(getattr(raw, "input_tokens", 0) or 0),
            output_tokens=int(getattr(raw, "output_tokens", 0) or 0),
            cached_input_tokens=int(getattr(details, "cached_tokens", 0) or 0),
        )
        try:
            menu = json.loads(response.output_text)
        except (json.JSONDecodeError, TypeError, AttributeError):
            return ReadResult(
                menu=None,
                usage=usage,
                model=self.model,
                latency_s=latency,
                error="resposta não é JSON",
            )
        return ReadResult(menu=menu, usage=usage, model=self.model, latency_s=latency)
