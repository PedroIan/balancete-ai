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
from typing import List, Optional, Tuple

import pdfplumber
from pdf2image import convert_from_bytes
from PIL import Image

# Limiar mínimo de caracteres por página para considerar o PDF como "com texto"
_LIMIAR_CHARS_POR_PAGINA = 50

# DPI de conversão de PDFs escaneados. Aumente para 200 para melhor OCR (mais lento).
DPI_PADRAO = 150

# Thresholds do caminho rápido Tesseract → gemma4
_TESSERACT_CONFIANCA_MIN = 60.0  # % de confiança mínima
_TESSERACT_CHARS_MIN = 80        # caracteres mínimos de texto útil


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

    # PDF
    total = _contar_paginas(caminho)
    texto = _extrair_texto(caminho)
    chars_por_pagina = len(texto) / max(total, 1)

    if chars_por_pagina >= _LIMIAR_CHARS_POR_PAGINA:
        return ConteudoPDF(texto=texto, imagens=[], total_paginas=total)

    # PDF escaneado: converte para imagens
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


def _extrair_texto(caminho: Path) -> str:
    """Extrai texto completo usando pdfplumber (tabelas + texto corrido)."""
    partes: List[str] = []
    try:
        with pdfplumber.open(caminho) as pdf:
            for pagina in pdf.pages:
                # Tenta extrair tabelas primeiro para preservar estrutura
                tabelas = pagina.extract_tables()
                if tabelas:
                    for tabela in tabelas:
                        for linha in tabela:
                            celulas = [c or "" for c in linha]
                            partes.append("\t".join(celulas))
                texto_pagina = pagina.extract_text() or ""
                if texto_pagina.strip():
                    partes.append(texto_pagina)
    except Exception:
        pass
    return "\n".join(partes)


def _pdf_para_imagens(caminho: Path, dpi: int = DPI_PADRAO) -> List[Tuple[int, bytes]]:
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


def ocr_com_tesseract(img_bytes: bytes) -> Tuple[str, float]:
    """
    Tenta OCR com Tesseract (idioma: por) após pré-processamento OpenCV.
    Retorna (texto, confianca) com confianca em 0–100.
    Retorna ("", 0.0) se Tesseract ou OpenCV não estiverem instalados — sem erros.
    """
    try:
        import cv2
        import numpy as np
        import pytesseract
    except ImportError:
        return ("", 0.0)

    try:
        # Decodifica bytes → array OpenCV
        arr = np.frombuffer(img_bytes, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            return ("", 0.0)

        # Pré-processamento: escala de cinza + binarização adaptativa
        cinza = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        binario = cv2.adaptiveThreshold(
            cinza, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
        )

        # OCR com dados de confiança por palavra
        dados = pytesseract.image_to_data(
            binario,
            lang="por",
            output_type=pytesseract.Output.DICT,
        )

        confs = [
            int(c)
            for c in dados["conf"]
            if str(c).lstrip("-").isdigit() and int(c) >= 0
        ]
        palavras = [w for w in dados["text"] if w.strip()]
        texto = " ".join(palavras)
        confianca = sum(confs) / len(confs) if confs else 0.0

        return (texto.strip(), confianca)
    except Exception:
        return ("", 0.0)


def tesseract_disponivel() -> bool:
    """Verifica se o Tesseract está instalado e acessível."""
    try:
        import pytesseract
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False
