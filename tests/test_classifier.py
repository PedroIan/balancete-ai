"""
Testes unitários para core/classifier.py
Execute com: python tests/test_classifier.py
"""
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# Stub de ollama para rodar sem o servidor em execução
_ollama_stub = types.ModuleType("ollama")
_ollama_stub.chat = lambda **kw: {"message": {"content": "{}"}}
sys.modules.setdefault("ollama", _ollama_stub)

import json

from core.classifier import (
    _categorias_validas,
    _categorias_validas_set,
    _dividir_em_chunks,
    _normalizar_transacao,
    _parse_data,
    _parse_json_llm,
    _parse_valor,
    _processar_dados,
    _prompt_principal,
    _validar_cnpj,
    aplicar_regras_deterministicas,
)


def test_parse_valor():
    # Formato JSON padrão
    assert _parse_valor(1234.56) == 1234.56
    assert _parse_valor("1234.56") == 1234.56

    # Formato BR sem milhar
    assert _parse_valor("1234,56") == 1234.56

    # Formato BR com milhar
    assert _parse_valor("1.234,56") == 1234.56
    assert _parse_valor("12.345,67") == 12345.67

    # Formato US com milhar
    assert _parse_valor("1,234.56") == 1234.56

    # Com prefixo monetário
    assert _parse_valor("R$ 1.234,56") == 1234.56
    assert _parse_valor("R$1234,56") == 1234.56

    # Casos-limite
    assert _parse_valor(None) == 0.0
    assert _parse_valor("") == 0.0
    assert _parse_valor(0) == 0.0
    assert _parse_valor("-500,00") == 500.00

    print("✅ test_parse_valor passou")


def test_validar_cnpj():
    assert _validar_cnpj("00.000.000/0001-91") == ("00000000000191", True)
    assert _validar_cnpj("00000000000191") == ("00000000000191", True)
    assert _validar_cnpj("00000000000199")[1] == False
    assert _validar_cnpj("1234567")[1] == False
    assert _validar_cnpj(None) == ("", False)
    assert _validar_cnpj("") == ("", False)

    print("✅ test_validar_cnpj passou")


def test_prompt_principal():
    prompt = _prompt_principal()

    # Tipos de documento esperados pelo fluxo, incluindo cupom fiscal (térmica)
    for tipo in ("extrato_bancario", "comprovante", "recibo", "nota_fiscal", "cupom_fiscal", "outro"):
        assert tipo in prompt, f"prompt sem tipo {tipo}"

    # Campos novos devem estar documentados no prompt
    for campo in ("fonte_pagadora", "prestador_destino", "numero_documento"):
        assert campo in prompt, f"prompt sem campo {campo}"

    # Categorias do YAML presentes no prompt
    for cat in _categorias_validas():
        assert cat in prompt, f"prompt sem categoria {cat}"

    print("✅ test_prompt_principal passou")


def test_dividir_em_chunks():
    assert _dividir_em_chunks("abc", 100) == ["abc"]

    linhas = "\n".join(f"linha {i}" for i in range(100))
    chunks = _dividir_em_chunks(linhas, 200)
    assert len(chunks) > 1
    assert all(len(c) <= 200 for c in chunks)
    # Nenhuma linha cortada ao meio e nada perdido
    assert "\n".join(chunks).splitlines() == linhas.splitlines()

    print("✅ test_dividir_em_chunks passou")


def test_processar_dados():
    # Cupom fiscal gera transação (não é descartado como "outro")
    dados = {
        "tipo_documento": "cupom_fiscal",
        "transacoes": [{
            "data": "2026-05-10",
            "prestador_destino": "SUPERMERCADO ABC",
            "cnpj": None,
            "descricao": "Material de limpeza",
            "valor": 87.50,
            "tipo": "despesa",
            "categoria": "Material de Consumo",
        }],
    }
    txs, movs, aviso = _processar_dados(dados, "cupom.jpg")
    assert len(txs) == 1 and not movs and aviso is None
    assert txs[0]["categoria"] == "Material de Consumo"

    # Categoria inventada pelo LLM cai no fallback da lista fechada
    dados = {
        "tipo_documento": "comprovante",
        "transacoes": [{
            "data": "2026-05-10",
            "prestador_destino": "QUALQUER",
            "descricao": "Serviço avulso",
            "valor": 10.0,
            "tipo": "despesa",
            "categoria": "Luz e Energia",
        }],
    }
    txs, _, _ = _processar_dados(dados, "doc.pdf")
    assert txs[0]["categoria"] == "Outras Despesas"

    # dados=None → aviso, nunca descarte silencioso
    txs, movs, aviso = _processar_dados(None, "doc.pdf")
    assert txs == [] and movs == [] and aviso is not None

    # Tipo "outro" → aviso
    txs, movs, aviso = _processar_dados({"tipo_documento": "outro", "transacoes": []}, "doc.pdf")
    assert txs == [] and movs == [] and aviso is not None

    print("✅ test_processar_dados passou")


def test_parse_json_llm():
    assert _parse_json_llm('{"a": 1}') == {"a": 1}
    assert _parse_json_llm('```json\n{"a": 1}\n```') == {"a": 1}
    assert _parse_json_llm('Claro! Aqui está: {"a": 1}') == {"a": 1}
    assert _parse_json_llm("nenhum json aqui") is None
    assert _parse_json_llm("[1, 2, 3]") is None  # lista não é o schema esperado

    print("✅ test_parse_json_llm passou")


def test_parse_data():
    assert _parse_data(None) is None
    assert _parse_data("") is None
    assert _parse_data("null") is None
    assert _parse_data("none") is None
    assert _parse_data("2026-05-10") == "2026-05-10"
    assert _parse_data("10/05/2026") == "2026-05-10"
    assert _parse_data("10-05-2026") == "2026-05-10"
    assert _parse_data("2026/05/10") == "2026-05-10"

    print("✅ test_parse_data passou")


def test_normalizar_transacao_novos_campos():
    dado = {
        "data": "2026-06-01",
        "fonte_pagadora": "CONDOMINIO XYZ",
        "prestador_destino": "CEMIG DISTRIBUICAO",
        "cnpj": None,
        "descricao": "Energia elétrica junho",
        "numero_documento": "NF-001234",
        "valor": 450.00,
        "tipo": "despesa",
        "categoria": "Energia Elétrica",
    }
    tx = _normalizar_transacao(dado, "nf.pdf")
    assert tx["fonte_pagadora"] == "CONDOMINIO XYZ"
    assert tx["prestador_destino"] == "CEMIG DISTRIBUICAO"
    assert tx["numero_documento"] == "NF-001234"
    assert tx["data"] == "2026-06-01"
    assert tx["valor"] == 450.00
    assert tx["suspeito"] is False
    assert "fornecedor" not in tx

    print("✅ test_normalizar_transacao_novos_campos passou")


def test_normalizar_transacao_data_ausente_marca_suspeito():
    dado = {
        "data": None,
        "prestador_destino": "FORNECEDOR X",
        "descricao": "Serviço prestado",
        "valor": 100.0,
        "tipo": "despesa",
        "categoria": "Administração",
    }
    tx = _normalizar_transacao(dado, "doc.pdf")
    assert tx["data"] is None
    assert tx["suspeito"] is True

    print("✅ test_normalizar_transacao_data_ausente_marca_suspeito passou")


def test_normalizar_transacao_legado_fornecedor():
    # LLM retorna campo legado "fornecedor" — deve virar "prestador_destino"
    dado = {
        "data": "2026-05-15",
        "fornecedor": "COPASA MG",
        "descricao": "Água e esgoto",
        "valor": 120.0,
        "tipo": "despesa",
        "categoria_sugerida": "Água e Esgoto",
    }
    tx = _normalizar_transacao(dado, "nf.pdf")
    assert tx["prestador_destino"] == "COPASA MG"
    assert tx["categoria"] == "Água e Esgoto"

    print("✅ test_normalizar_transacao_legado_fornecedor passou")


def test_regras_deterministicas_prioridade():
    # CEMIG é regra determinística → ignora categoria do LLM
    dado = {
        "data": "2026-05-20",
        "prestador_destino": "CEMIG",
        "descricao": "Fatura maio",
        "valor": 300.0,
        "tipo": "despesa",
        "categoria": "Outras Despesas",  # LLM errou a categoria
    }
    tx = _normalizar_transacao(dado, "nf.pdf")
    assert tx["categoria"] == "Energia Elétrica"
    assert tx["tipo"] == "despesa"

    print("✅ test_regras_deterministicas_prioridade passou")


def test_categorias_validas_nao_vazio():
    cats = _categorias_validas()
    assert len(cats) > 0
    cats_set = _categorias_validas_set()
    assert "Outras Despesas" in cats_set
    assert "Outras Receitas" in cats_set
    for c in cats:
        assert c in cats_set

    print("✅ test_categorias_validas_nao_vazio passou")


if __name__ == "__main__":
    test_parse_valor()
    test_validar_cnpj()
    test_prompt_principal()
    test_dividir_em_chunks()
    test_processar_dados()
    test_parse_json_llm()
    test_parse_data()
    test_normalizar_transacao_novos_campos()
    test_normalizar_transacao_data_ausente_marca_suspeito()
    test_normalizar_transacao_legado_fornecedor()
    test_regras_deterministicas_prioridade()
    test_categorias_validas_nao_vazio()
    print("\n✅ Todos os testes de classifier passaram")
