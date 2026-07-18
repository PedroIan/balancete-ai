"""
core/classifier.py
Classificação e extração de transações via LLM local (Ollama).
Única camada que conversa com o Ollama — extractor e conciliacao não conhecem LLM.
"""

from __future__ import annotations

import json
import os
import re
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import ollama
import yaml

TEXTO_MODEL = os.getenv("BALANCETE_TEXTO_MODEL", "gemma4:e4b")
VISAO_MODEL = os.getenv("BALANCETE_VISAO_MODEL", "qwen3-vl:8b")
LLM_NUM_PREDICT = int(os.getenv("BALANCETE_LLM_NUM_PREDICT", "4096"))
LLM_NUM_CTX = int(os.getenv("BALANCETE_LLM_NUM_CTX", "8192"))
_MAX_CHARS_LLM = 12_000

_RE_FINANCEIRO = re.compile(
    r"R\$|\bvalor\b|\bpagamento\b|\bfatura\b|\bnota fiscal\b|\brecibo\b"
    r"|\bdébito\b|\bcrédito\b|\bvencimento\b|\bextrato\b|\bsaldo\b",
    re.IGNORECASE,
)

_PROMPT_FALLBACK = """Extraia os dados financeiros do documento abaixo.
Retorne APENAS um JSON válido, sem texto adicional.

{
  "tipo_documento": "comprovante",
  "transacoes": [
    {
      "data": null,
      "fonte_pagadora": "quem pagou",
      "prestador_destino": "quem recebeu",
      "cnpj": null,
      "descricao": "descricao do servico",
      "numero_documento": "",
      "valor": 0.00,
      "tipo": "despesa",
      "categoria": "Outras Despesas"
    }
  ]
}

Documento:
"""


@lru_cache(maxsize=1)
def _carregar_regras() -> List[Dict]:
    yml_path = Path(__file__).parent.parent / "config" / "categorias.yml"
    with open(yml_path, encoding="utf-8") as f:
        dados = yaml.safe_load(f)
    return dados.get("regras", [])


@lru_cache(maxsize=1)
def _categorias_validas() -> Tuple[str, ...]:
    return tuple(dict.fromkeys(r["categoria"] for r in _carregar_regras()))


@lru_cache(maxsize=1)
def _categorias_validas_set() -> frozenset:
    return frozenset(_categorias_validas()) | {"Outras Despesas", "Outras Receitas"}


@lru_cache(maxsize=1)
def _prompt_principal() -> str:
    cats = ", ".join(_categorias_validas())
    return (
        "Voce eh um extrator de dados financeiros de condominios brasileiros.\n"
        "Identifique o tipo do documento e extraia os dados.\n"
        "Retorne APENAS um JSON valido, sem markdown e sem texto adicional.\n\n"
        "tipo_documento (escolha exatamente um):\n"
        '- "extrato_bancario": listagem de movimentacoes de conta bancaria em um periodo\n'
        '- "comprovante": comprovante de pagamento efetuado (boleto, PIX, TED)\n'
        '- "recibo": confirmacao de recebimento emitida pelo recebedor\n'
        '- "nota_fiscal": NF-e, NFC-e, NFS-e ou DANFE\n'
        '- "cupom_fiscal": cupom de impressora termica (layout estreito, CNPJ no rodape)\n'
        '- "outro": documento sem dados financeiros identificaveis\n\n'
        f"Categorias validas (use EXATAMENTE uma): {cats}, Outras Despesas, Outras Receitas.\n\n"
        "Campos para comprovante/recibo/nota_fiscal/cupom_fiscal:\n"
        "- fonte_pagadora: quem pagou (nome do condominio, empresa ou pessoa fisica)\n"
        "- prestador_destino: quem recebeu (empresa, prestador, fornecedor)\n"
        "- cnpj: CNPJ do recebedor somente com digitos, ou null se ausente\n"
        "- numero_documento: numero da NF, recibo ou protocolo, ou string vazia se ausente\n"
        "- data: data em AAAA-MM-DD, ou null se nao encontrar no documento\n"
        "- valor: float positivo com ponto decimal\n"
        '- tipo: "receita" ou "despesa"\n'
        "- categoria: exatamente uma das categorias validas acima\n\n"
        'Formato para extrato_bancario:\n{"tipo_documento": "extrato_bancario", "movimentacoes": ['
        '{"data": "AAAA-MM-DD", "descricao": "texto", "valor": 0.00, "tipo": "credito", "saldo": null}]}\n\n'
        'Formato para comprovante/recibo/nota_fiscal/cupom_fiscal:\n{"tipo_documento": "comprovante", "transacoes": ['
        '{"data": "AAAA-MM-DD ou null", "fonte_pagadora": "pagador", "prestador_destino": "recebedor", '
        '"cnpj": "digitos ou null", "descricao": "servico", "numero_documento": "", '
        '"valor": 0.00, "tipo": "despesa", "categoria": "categoria exata"}]}\n\n'
        'Formato para outro: {"tipo_documento": "outro", "transacoes": []}\n\n'
        "Regras:\n"
        "- Comprovantes, recibos e notas sao QUASE SEMPRE despesa.\n"
        "- credito = entrada na conta; debito = saida da conta.\n"
        "- Valores sempre positivos. Campo ilegivel ou ausente = null.\n\n"
        "Documento a analisar:\n"
    )


def aplicar_regras_deterministicas(
    prestador: Optional[str], descricao: Optional[str]
) -> Tuple[Optional[str], Optional[str]]:
    texto = " ".join(filter(None, [prestador, descricao])).upper()
    if not texto.strip():
        return (None, None)
    for regra in _carregar_regras():
        padrao = regra.get("padrao", "")
        try:
            if re.search(padrao, texto, re.IGNORECASE):
                return (regra["categoria"], regra["tipo"])
        except re.error:
            continue
    return (None, None)


def extrair_de_texto(
    texto: str, fonte: str
) -> Tuple[List[Dict], List[Dict], Optional[str]]:
    txs: List[Dict] = []
    movs: List[Dict] = []
    avisos: List[str] = []
    for chunk in _dividir_em_chunks(texto, _MAX_CHARS_LLM):
        dados = _chamar_llm_texto_com_retry(chunk)
        c_txs, c_movs, c_aviso = _processar_dados(dados, fonte)
        txs.extend(c_txs)
        movs.extend(c_movs)
        if c_aviso:
            avisos.append(c_aviso)
    aviso = "; ".join(avisos) if avisos and not (txs or movs) else None
    return (txs, movs, aviso)


def extrair_de_imagem(
    img_b64: str, fonte: str
) -> Tuple[List[Dict], List[Dict], Optional[str]]:
    dados = _chamar_llm_visao_com_retry(img_b64)
    return _processar_dados(dados, fonte)


def _chamar_llm_texto_com_retry(texto: str) -> Optional[Dict]:
    resposta = _llm_texto(_prompt_principal() + texto)
    dados = _parse_json_llm(resposta)
    if (dados is None or dados.get("tipo_documento") == "outro") and _RE_FINANCEIRO.search(texto):
        resposta2 = _llm_texto(_PROMPT_FALLBACK + texto)
        dados2 = _parse_json_llm(resposta2)
        if dados2 is not None and dados2.get("tipo_documento") != "outro":
            return dados2
    return dados


def _chamar_llm_visao_com_retry(img_b64: str) -> Optional[Dict]:
    resposta = _llm_visao(img_b64, _prompt_principal())
    dados = _parse_json_llm(resposta)
    if dados is None or dados.get("tipo_documento") == "outro":
        resposta2 = _llm_visao(img_b64, _PROMPT_FALLBACK)
        dados2 = _parse_json_llm(resposta2)
        if dados2 is not None and dados2.get("tipo_documento") != "outro":
            return dados2
    return dados


def _dividir_em_chunks(texto: str, max_chars: int) -> List[str]:
    if len(texto) <= max_chars:
        return [texto]
    chunks: List[str] = []
    atual: List[str] = []
    tamanho = 0
    for linha in texto.splitlines():
        if len(linha) > max_chars:
            linha = linha[:max_chars]
        if tamanho + len(linha) + 1 > max_chars and atual:
            chunks.append("\n".join(atual))
            atual = []
            tamanho = 0
        atual.append(linha)
        tamanho += len(linha) + 1
    if atual:
        chunks.append("\n".join(atual))
    return chunks


def _llm_texto(prompt: str) -> str:
    try:
        resposta = ollama.chat(
            model=TEXTO_MODEL,
            format="json",
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": 0, "num_predict": LLM_NUM_PREDICT, "num_ctx": LLM_NUM_CTX},
        )
        return resposta["message"]["content"]
    except Exception as exc:
        raise RuntimeError(
            f"Erro no modelo de texto ({TEXTO_MODEL}): {exc}. "
            "Verifique se o Ollama esta rodando e o modelo esta instalado."
        ) from exc


def _llm_visao(img_b64: str, prompt_base: str) -> str:
    try:
        resposta = ollama.chat(
            model=VISAO_MODEL,
            format="json",
            messages=[{
                "role": "user",
                "content": prompt_base + "Analise a imagem do documento.",
                "images": [img_b64],
            }],
            options={"temperature": 0, "num_predict": LLM_NUM_PREDICT, "num_ctx": LLM_NUM_CTX},
        )
        return resposta["message"]["content"]
    except Exception as exc:
        raise RuntimeError(
            f"Erro no modelo de visao ({VISAO_MODEL}): {exc}. "
            "Verifique se o Ollama esta rodando e o modelo esta instalado."
        ) from exc


def _processar_dados(
    dados: Optional[Dict], fonte: str
) -> Tuple[List[Dict], List[Dict], Optional[str]]:
    if dados is None:
        return ([], [], "resposta do modelo nao e um JSON interpretavel")
    tipo_doc = dados.get("tipo_documento", "outro")
    if tipo_doc == "extrato_bancario":
        movs = [_normalizar_movimentacao(m, fonte) for m in dados.get("movimentacoes", []) if isinstance(m, dict)]
        return ([], movs, None)
    if tipo_doc in {"comprovante", "recibo", "nota_fiscal", "cupom_fiscal"}:
        txs = [_normalizar_transacao(t, fonte) for t in dados.get("transacoes", []) if isinstance(t, dict)]
        return (txs, [], None)
    return ([], [], 'documento classificado como "outro" - nenhum dado financeiro identificado')


def _parse_json_llm(texto: str) -> Optional[Dict]:
    texto = texto.strip()
    try:
        dados = json.loads(texto)
        if isinstance(dados, dict):
            return dados
    except json.JSONDecodeError:
        pass
    match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", texto)
    if match:
        try:
            dados = json.loads(match.group(1))
            if isinstance(dados, dict):
                return dados
        except json.JSONDecodeError:
            pass
    match = re.search(r"\{[\s\S]+\}", texto)
    if match:
        try:
            dados = json.loads(match.group(0))
            if isinstance(dados, dict):
                return dados
        except json.JSONDecodeError:
            pass
    return None


def _normalizar_transacao(dado: Dict, fonte: str) -> Dict:
    fonte_pagadora = (dado.get("fonte_pagadora") or "").strip()
    prestador_destino = (dado.get("prestador_destino") or dado.get("fornecedor") or "").strip()
    descricao = (dado.get("descricao") or "").strip()
    numero_documento = (dado.get("numero_documento") or "").strip()
    valor = abs(_parse_valor(dado.get("valor")))
    data = _parse_data(dado.get("data"))
    tipo = dado.get("tipo", "despesa")
    if tipo not in {"receita", "despesa"}:
        tipo = "despesa"
    cnpj_raw, cnpj_valido = _validar_cnpj(dado.get("cnpj"))
    cat_det, tipo_det = aplicar_regras_deterministicas(prestador_destino, descricao)
    if cat_det:
        categoria = cat_det
        tipo = tipo_det
    else:
        categoria_llm = (dado.get("categoria") or dado.get("categoria_sugerida") or "").strip()
        if categoria_llm and categoria_llm in _categorias_validas_set():
            categoria = categoria_llm
        else:
            categoria = "Outras Receitas" if tipo == "receita" else "Outras Despesas"
    suspeito = (
        valor == 0.0
        or data is None
        or not descricao
        or (bool(cnpj_raw) and not cnpj_valido)
    )
    return {
        "data": data,
        "fonte_pagadora": fonte_pagadora,
        "prestador_destino": prestador_destino,
        "cnpj": cnpj_raw,
        "descricao": descricao,
        "numero_documento": numero_documento,
        "valor": valor,
        "tipo": tipo,
        "categoria": categoria,
        "suspeito": suspeito,
        "fonte": fonte,
    }


def _normalizar_movimentacao(dado: Dict, fonte: str) -> Dict:
    valor = abs(_parse_valor(dado.get("valor")))
    tipo = dado.get("tipo", "debito")
    if tipo not in {"credito", "debito"}:
        tipo = "debito"
    saldo_raw = dado.get("saldo")
    saldo = abs(_parse_valor(saldo_raw)) if saldo_raw is not None else None
    return {
        "data": _parse_data(dado.get("data")) or date.today().isoformat(),
        "descricao": (dado.get("descricao") or "").strip(),
        "valor": valor,
        "tipo": tipo,
        "saldo": saldo,
        "fonte": fonte,
    }


def _parse_valor(valor) -> float:
    if valor is None:
        return 0.0
    if isinstance(valor, (int, float)):
        return abs(float(valor))
    s = str(valor).strip()
    s = re.sub(r"[R$\s]", "", s)
    if not s:
        return 0.0
    tem_ponto = "." in s
    tem_virgula = "," in s
    if tem_ponto and tem_virgula:
        if s.rindex(".") > s.rindex(","):
            s = s.replace(",", "")
        else:
            s = s.replace(".", "").replace(",", ".")
    elif tem_virgula:
        s = s.replace(",", ".")
    elif tem_ponto:
        partes = s.split(".")
        if len(partes) == 2 and len(partes[1]) == 3:
            s = s.replace(".", "")
    try:
        return abs(float(s))
    except (ValueError, TypeError):
        return 0.0


def _parse_data(data_str) -> Optional[str]:
    if not data_str:
        return None
    s = str(data_str).strip()
    if s.lower() in {"null", "none", ""}:
        return None
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        return s
    m = re.fullmatch(r"(\d{2})/(\d{2})/(\d{4})", s)
    if m:
        return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    m = re.fullmatch(r"(\d{2})-(\d{2})-(\d{4})", s)
    if m:
        return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    m = re.fullmatch(r"(\d{4})/(\d{2})/(\d{2})", s)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return None


def _validar_cnpj(cnpj_raw) -> Tuple[str, bool]:
    if not cnpj_raw:
        return ("", False)
    digitos = re.sub(r"\D", "", str(cnpj_raw))
    if len(digitos) != 14:
        return (digitos, False)
    if len(set(digitos)) == 1:
        return (digitos, False)

    def _calcular_digito(digitos_base: str, pesos: List[int]) -> int:
        soma = sum(int(d) * p for d, p in zip(digitos_base, pesos))
        resto = soma % 11
        return 0 if resto < 2 else 11 - resto

    pesos1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    pesos2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    d1 = _calcular_digito(digitos[:12], pesos1)
    d2 = _calcular_digito(digitos[:13], pesos2)
    valido = (int(digitos[12]) == d1) and (int(digitos[13]) == d2)
    return (digitos, valido)
