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

# Modelos configuráveis por env var — máquinas locais variam em VRAM e modelos
# disponíveis no Ollama.
TEXTO_MODEL = os.getenv("BALANCETE_TEXTO_MODEL", "gemma4:e4b")
VISAO_MODEL = os.getenv("BALANCETE_VISAO_MODEL", "qwen3-vl:8b")

# Limite de tokens gerados — evita geração infinita quando o modelo degenera.
LLM_NUM_PREDICT = int(os.getenv("BALANCETE_LLM_NUM_PREDICT", "4096"))

# Janela de contexto. O default do Ollama (~2048) trunca extratos longos
# silenciosamente. 8192 cobre ~12k chars de entrada; aumentar consome mais VRAM.
LLM_NUM_CTX = int(os.getenv("BALANCETE_LLM_NUM_CTX", "8192"))

# Máximo de caracteres de documento por chamada — calibrado para caber em
# LLM_NUM_CTX junto com o prompt. Textos maiores são divididos em chunks.
_MAX_CHARS_LLM = 12_000

# Lista fechada de categorias (REGRAS_DE_NEGOCIO.md §2). O prompt instrui o LLM
# a escolher só destas; a normalização rejeita qualquer outra.
CATEGORIAS_DESPESA = (
    "Pessoal e Encargos",
    "Manutenção",
    "Limpeza",
    "Energia Elétrica",
    "Água e Esgoto",
    "Seguro",
    "Administração",
    "Material de Consumo",
    "Serviços Contratados",
    "Tributos",
    "Outras Despesas",
)
CATEGORIAS_RECEITA = (
    "Condomínio",
    "Cota Extra",
    "Fundo de Reserva",
    "Multas e Juros",
    "Taxa de Mudança",
    "Outras Receitas",
)
_CATEGORIAS_VALIDAS = set(CATEGORIAS_DESPESA) | set(CATEGORIAS_RECEITA)

_PROMPT_UNIFICADO = f"""Você é um extrator de dados financeiros de condomínios brasileiros.
Identifique o tipo do documento e extraia os dados.
Retorne APENAS um JSON válido, sem markdown e sem texto adicional.

tipo_documento (escolha exatamente um):
- "extrato_bancario": listagem de movimentações de conta bancária em um período
- "comprovante": comprovante de pagamento efetuado (boleto, PIX, TED)
- "recibo": confirmação de recebimento emitida pelo recebedor
- "nota_fiscal": NF-e, NFC-e, NFS-e ou DANFE
- "cupom_fiscal": cupom de impressora térmica (layout estreito, fonte pequena, comum em mercados e farmácias; o CNPJ costuma aparecer no rodapé)
- "outro": documento sem dados financeiros identificáveis

Formato para extrato_bancario:
{{
  "tipo_documento": "extrato_bancario",
  "movimentacoes": [
    {{
      "data": "AAAA-MM-DD",
      "descricao": "texto",
      "valor": 0.00,
      "tipo": "credito" ou "debito",
      "saldo": 0.00 ou null
    }}
  ]
}}

Formato para comprovante, recibo, nota_fiscal e cupom_fiscal:
{{
  "tipo_documento": "comprovante",
  "transacoes": [
    {{
      "data": "AAAA-MM-DD",
      "fornecedor": "nome do estabelecimento/beneficiário",
      "cnpj": "somente digitos ou null",
      "descricao": "texto",
      "valor": 0.00,
      "tipo": "despesa" ou "receita",
      "categoria_sugerida": "uma das categorias listadas abaixo"
    }}
  ]
}}

Formato para documento sem dados:
{{
  "tipo_documento": "outro",
  "transacoes": []
}}

categoria_sugerida — use EXATAMENTE uma destas:
- Para despesa: {" | ".join(CATEGORIAS_DESPESA)}
- Para receita: {" | ".join(CATEGORIAS_RECEITA)}

Regras:
- Comprovantes, recibos, notas fiscais e cupons fiscais são QUASE SEMPRE "despesa". Use "receita" apenas se for claramente um recebimento do condomínio (ex: taxa condominial paga por morador).
- "credito" = entrada na conta bancária; "debito" = saída da conta bancária.
- Valores sempre positivos (float), com ponto decimal. Datas no formato AAAA-MM-DD.
- Não invente dados: campo ilegível ou ausente = null.

Documento a analisar:
"""


@lru_cache(maxsize=1)
def _carregar_regras() -> List[Dict]:
    """Carrega e faz cache das regras determinísticas do categorias.yml."""
    yml_path = Path(__file__).parent.parent / "config" / "categorias.yml"
    with open(yml_path, encoding="utf-8") as f:
        dados = yaml.safe_load(f)
    return dados.get("regras", [])


def aplicar_regras_deterministicas(
    fornecedor: Optional[str], descricao: Optional[str]
) -> Tuple[Optional[str], Optional[str]]:
    """
    Tenta categorizar via regras do categorias.yml.
    Retorna (categoria, tipo) ou (None, None) se nenhuma regra bater.
    """
    texto = " ".join(filter(None, [fornecedor, descricao])).upper()
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


def extrair_de_texto(texto: str, fonte: str) -> Tuple[List[Dict], List[Dict], Optional[str]]:
    """
    Entry point para PDFs com texto extraível.
    Textos maiores que _MAX_CHARS_LLM são divididos em chunks (uma chamada cada).
    Retorna (transacoes, extrato_movs, aviso). `aviso` é None quando tudo correu bem.
    """
    txs: List[Dict] = []
    movs: List[Dict] = []
    avisos: List[str] = []

    for chunk in _dividir_em_chunks(texto, _MAX_CHARS_LLM):
        resposta = _llm_texto(chunk)
        c_txs, c_movs, c_aviso = _processar_resposta(resposta, fonte)
        txs.extend(c_txs)
        movs.extend(c_movs)
        if c_aviso:
            avisos.append(c_aviso)

    aviso = "; ".join(avisos) if avisos and not (txs or movs) else None
    return (txs, movs, aviso)


def extrair_de_imagem(img_b64: str, fonte: str) -> Tuple[List[Dict], List[Dict], Optional[str]]:
    """
    Entry point para PDFs escaneados e imagens diretas.
    Retorna (transacoes, extrato_movs, aviso). `aviso` é None quando tudo correu bem.
    """
    resposta = _llm_visao(img_b64)
    return _processar_resposta(resposta, fonte)


def _dividir_em_chunks(texto: str, max_chars: int) -> List[str]:
    """
    Divide o texto em chunks de até max_chars, quebrando em linhas inteiras
    para não cortar uma movimentação de extrato ao meio.
    """
    if len(texto) <= max_chars:
        return [texto]

    chunks: List[str] = []
    atual: List[str] = []
    tamanho = 0

    for linha in texto.splitlines():
        # Linha individual maior que o limite: corta à força
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


def _llm_texto(texto: str) -> str:
    """Chama o modelo de texto via Ollama com saída JSON forçada."""
    prompt = _PROMPT_UNIFICADO + texto
    try:
        resposta = ollama.chat(
            model=TEXTO_MODEL,
            format="json",
            messages=[{"role": "user", "content": prompt}],
            options={
                "temperature": 0,
                "num_predict": LLM_NUM_PREDICT,
                "num_ctx": LLM_NUM_CTX,
            },
        )
        return resposta["message"]["content"]
    except Exception as exc:
        raise RuntimeError(
            f"Erro no modelo de texto ({TEXTO_MODEL}): {exc}. "
            "Verifique se o Ollama está rodando e o modelo está instalado."
        ) from exc


def _llm_visao(img_b64: str) -> str:
    """Chama o modelo de visão via Ollama com imagem em base64 e saída JSON forçada."""
    try:
        resposta = ollama.chat(
            model=VISAO_MODEL,
            format="json",
            messages=[
                {
                    "role": "user",
                    "content": _PROMPT_UNIFICADO + "Analise a imagem do documento.",
                    "images": [img_b64],
                }
            ],
            options={
                "temperature": 0,
                "num_predict": LLM_NUM_PREDICT,
                "num_ctx": LLM_NUM_CTX,
            },
        )
        return resposta["message"]["content"]
    except Exception as exc:
        raise RuntimeError(
            f"Erro no modelo de visão ({VISAO_MODEL}): {exc}. "
            "Verifique se o Ollama está rodando e o modelo está instalado."
        ) from exc


def _processar_resposta(
    resposta_bruta: str, fonte: str
) -> Tuple[List[Dict], List[Dict], Optional[str]]:
    """
    Parseia o JSON do LLM e normaliza para as estruturas internas.
    Retorna (transacoes, extrato_movs, aviso) — aviso preenchido quando o
    documento foi descartado (JSON inválido ou tipo "outro"), para a UI
    sinalizar em vez de descartar silenciosamente.
    """
    dados = _parse_json_llm(resposta_bruta)
    if dados is None:
        return ([], [], "resposta do modelo não é um JSON interpretável")

    tipo_doc = dados.get("tipo_documento", "outro")

    if tipo_doc == "extrato_bancario":
        movs = [
            _normalizar_movimentacao(m, fonte)
            for m in dados.get("movimentacoes", [])
            if isinstance(m, dict)
        ]
        return ([], movs, None)

    if tipo_doc in {"comprovante", "recibo", "nota_fiscal", "cupom_fiscal"}:
        txs = [
            _normalizar_transacao(t, fonte)
            for t in dados.get("transacoes", [])
            if isinstance(t, dict)
        ]
        return (txs, [], None)

    return ([], [], 'documento classificado como "outro" — nenhum dado financeiro identificado')


def _parse_json_llm(texto: str) -> Optional[Dict]:
    """
    Extrai JSON da resposta bruta do LLM (que pode ter texto ao redor).
    Retorna None quando nenhuma estratégia produz um JSON válido.
    """
    # Tenta parse direto
    texto = texto.strip()
    try:
        dados = json.loads(texto)
        if isinstance(dados, dict):
            return dados
    except json.JSONDecodeError:
        pass

    # Tenta extrair bloco JSON do markdown
    match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", texto)
    if match:
        try:
            dados = json.loads(match.group(1))
            if isinstance(dados, dict):
                return dados
        except json.JSONDecodeError:
            pass

    # Tenta encontrar o primeiro { ... } válido
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
    """Monta um dict de transação tipado a partir do JSON bruto do LLM."""
    fornecedor = (dado.get("fornecedor") or "").strip()
    descricao = (dado.get("descricao") or "").strip()
    valor = abs(_parse_valor(dado.get("valor")))
    data = _parse_data(dado.get("data"))
    tipo = dado.get("tipo", "despesa")
    if tipo not in {"receita", "despesa"}:
        tipo = "despesa"

    cnpj_raw, cnpj_valido = _validar_cnpj(dado.get("cnpj"))

    # Regras determinísticas têm prioridade sobre LLM
    cat_det, tipo_det = aplicar_regras_deterministicas(fornecedor, descricao)
    if cat_det:
        categoria = cat_det
        tipo = tipo_det
    else:
        # Categoria do LLM só vale se estiver na lista fechada — modelos
        # pequenos inventam variações ("Energia", "Luz") que poluem o XLSX.
        categoria_llm = (dado.get("categoria_sugerida") or "").strip()
        if categoria_llm in _CATEGORIAS_VALIDAS:
            categoria = categoria_llm
        else:
            categoria = "Outras Receitas" if tipo == "receita" else "Outras Despesas"

    suspeito = (
        valor == 0.0
        or not data
        or not descricao
        or (bool(cnpj_raw) and not cnpj_valido)
    )

    return {
        "data": data or date.today().isoformat(),
        "fornecedor": fornecedor,
        "cnpj": cnpj_raw,
        "descricao": descricao,
        "valor": valor,
        "tipo": tipo,
        "categoria": categoria,
        "suspeito": suspeito,
        "fonte": fonte,
    }


def _normalizar_movimentacao(dado: Dict, fonte: str) -> Dict:
    """Monta um dict de movimentação de extrato a partir do JSON bruto do LLM."""
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
    """
    Converte formatos BR/US/JSON para float.
    Sempre retorna positivo — o tipo da transação define a direção.
    """
    if valor is None:
        return 0.0
    if isinstance(valor, (int, float)):
        return abs(float(valor))

    s = str(valor).strip()
    # Remove prefixo monetário e espaços
    s = re.sub(r"[R$\s]", "", s)
    if not s:
        return 0.0

    tem_ponto = "." in s
    tem_virgula = "," in s

    if tem_ponto and tem_virgula:
        # Descobre qual é separador decimal pela posição relativa
        if s.rindex(".") > s.rindex(","):
            # US: 1,234.56
            s = s.replace(",", "")
        else:
            # BR: 1.234,56
            s = s.replace(".", "").replace(",", ".")
    elif tem_virgula:
        # BR sem milhar: 1234,56
        s = s.replace(",", ".")
    elif tem_ponto:
        partes = s.split(".")
        if len(partes) == 2 and len(partes[1]) == 3:
            # Ponto como separador de milhar: 1.234
            s = s.replace(".", "")

    try:
        return abs(float(s))
    except (ValueError, TypeError):
        return 0.0


def _parse_data(data_str) -> Optional[str]:
    """Tenta interpretar a data e retorna no formato AAAA-MM-DD ou None."""
    if not data_str:
        return None
    s = str(data_str).strip()

    # Já está no formato ISO
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        return s

    # DD/MM/AAAA
    m = re.fullmatch(r"(\d{2})/(\d{2})/(\d{4})", s)
    if m:
        return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"

    # DD-MM-AAAA
    m = re.fullmatch(r"(\d{2})-(\d{2})-(\d{4})", s)
    if m:
        return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"

    # AAAA/MM/DD
    m = re.fullmatch(r"(\d{4})/(\d{2})/(\d{2})", s)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"

    return None


def _validar_cnpj(cnpj_raw) -> Tuple[str, bool]:
    """
    Valida CNPJ com dígitos verificadores.
    Retorna (cnpj_14_digitos, valido).
    """
    if not cnpj_raw:
        return ("", False)

    # Remove formatação
    digitos = re.sub(r"\D", "", str(cnpj_raw))

    if len(digitos) != 14:
        return (digitos, False)

    if len(set(digitos)) == 1:
        # CNPJ com todos dígitos iguais é inválido
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
