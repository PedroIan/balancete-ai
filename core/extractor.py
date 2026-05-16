"""
core/extractor.py
Extração de conteúdo bruto de PDFs e imagens — sem LLM, sem regras de negócio.
"""

from __future__ import annotations

import base64
import io
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Tuple

import pdfplumber
from pdf2image import convert_from_bytes
from PIL import Image


@dataclass
class ConteudoPDF:
    """Resultado da extração de um arquivo PDF ou imagem."""

    texto: str = ""
    imagens: List[Tuple[int, bytes]] = field(default_factory=list)
    total_paginas: int = 0

    @property
    def tem_texto(self) -> bool:
        return bool(self.texto.strip())


def extrair_conteudo_pdf(caminho: str | Path) -> ConteudoPDF:
    """Entry point principal — decide automaticamente entre extração de texto e OCR por imagem."""
    caminho = Path(caminho)
    sufixo = caminho.suffix.lower()

    if sufixo in {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff", ".tif"}:
        imagem_bytes = caminho.read_bytes()
        return ConteudoPDF(
            texto="",
            imagens=[(1, imagem_bytes)],
            total_paginas=1,
        )

    # PDF — always convert pages to images for the image extraction pipeline
    total = _contar_paginas(caminho)
    imagens = _pdf_para_imagens(caminho)
    return ConteudoPDF(texto="", imagens=imagens, total_paginas=total)


def _contar_paginas(caminho: Path) -> int:
    """Conta páginas usando pdfinfo (rápido) com fallback para pdfplumber."""
    try:
        resultado = subprocess.run(
            ["pdfinfo", str(caminho)],
            capture_output=True,
            text=True,
            timeout=10,
        )
        for linha in resultado.stdout.splitlines():
            if linha.lower().startswith("pages:"):
                return int(linha.split(":")[1].strip())
    except Exception:
        pass

    try:
        with pdfplumber.open(caminho) as pdf:
            return len(pdf.pages)
    except Exception:
        return 0


def _pdf_para_imagens(caminho: Path, dpi: int = 150) -> List[Tuple[int, bytes]]:
    """Converte cada página do PDF em PNG (página por página para evitar OOM)."""
    pdf_bytes = caminho.read_bytes()
    resultado: List[Tuple[int, bytes]] = []

    try:
        paginas = convert_from_bytes(pdf_bytes, dpi=dpi, fmt="png")
        for num, pagina in enumerate(paginas, start=1):
            buf = io.BytesIO()
            pagina.save(buf, format="PNG")
            resultado.append((num, buf.getvalue()))
    except Exception:
        pass

    return resultado


def carregar_imagem_b64(caminho: str | Path) -> str:
    """Lê um arquivo de imagem do disco e retorna base64."""
    return base64.b64encode(Path(caminho).read_bytes()).decode("utf-8")


def bytes_para_b64(dados: bytes) -> str:
    """Converte bytes de PNG/imagem para string base64."""
    return base64.b64encode(dados).decode("utf-8")
