"""
Testes unitários para core/classifier.py
Execute com: python tests/test_classifier.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.classifier import (
    _parse_valor,
    _parse_data,
    _validar_cnpj,
    _normalizar_transacao,
    _categorias_validas,
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


def test_parse_data():
    # Formato ISO
    assert _parse_data("2026-05-16") == "2026-05-16"

    # DD/MM/AAAA
    assert _parse_data("16/05/2026") == "2026-05-16"

    # DD-MM-AAAA
    assert _parse_data("16-05-2026") == "2026-05-16"

    # AAAA/MM/DD
    assert _parse_data("2026/05/16") == "2026-05-16"

    # Ausente — retorna None (não cai para date.today())
    assert _parse_data(None) is None
    assert _parse_data("") is None
    assert _parse_data("null") is None
    assert _parse_data("none") is None

    print("✅ test_parse_data passou")


def test_validar_cnpj():
    assert _validar_cnpj("00.000.000/0001-91") == ("00000000000191", True)
    assert _validar_cnpj("00000000000191") == ("00000000000191", True)
    assert _validar_cnpj("00000000000199")[1] == False
    assert _validar_cnpj("1234567")[1] == False
    assert _validar_cnpj(None) == ("", False)
    assert _validar_cnpj("") == ("", False)

    print("✅ test_validar_cnpj passou")


def test_normalizar_transacao_novos_campos():
    # Verifica que os novos campos são extraídos do JSON do LLM
    dado = {
        "data": "2026-05-01",
        "fonte_pagadora": "Condomínio Edifício Sol",
        "prestador_destino": "SABESP S.A.",
        "cnpj": "43776517000180",
        "descricao": "Conta de água maio/2026",
        "numero_documento": "NF-000123",
        "valor": 350.75,
        "tipo": "despesa",
        "categoria": "Água e Esgoto",
    }
    resultado = _normalizar_transacao(dado, "teste.pdf")

    assert resultado["data"] == "2026-05-01"
    assert resultado["fonte_pagadora"] == "Condomínio Edifício Sol"
    assert resultado["prestador_destino"] == "SABESP S.A."
    assert resultado["numero_documento"] == "NF-000123"
    assert resultado["valor"] == 350.75
    # Regra determinística de SABESP deve sobrescrever categoria
    assert resultado["categoria"] == "Água e Esgoto"
    assert resultado["tipo"] == "despesa"
    assert resultado["suspeito"] is False

    print("✅ test_normalizar_transacao_novos_campos passou")


def test_normalizar_transacao_data_ausente_marca_suspeito():
    # data=None deve marcar suspeito=True sem usar date.today()
    dado = {
        "data": None,
        "fonte_pagadora": "Cond. ABC",
        "prestador_destino": "Empresa XYZ",
        "cnpj": "",
        "descricao": "Serviço genérico",
        "numero_documento": "",
        "valor": 100.0,
        "tipo": "despesa",
        "categoria": "Outras Despesas",
    }
    resultado = _normalizar_transacao(dado, "teste.pdf")

    assert resultado["data"] is None, "data ausente deve ser None, não date.today()"
    assert resultado["suspeito"] is True, "data ausente deve marcar suspeito=True"

    print("✅ test_normalizar_transacao_data_ausente_marca_suspeito passou")


def test_normalizar_transacao_legado_fornecedor():
    # Compatibilidade com LLMs que ainda retornam "fornecedor" (prompt antigo)
    dado = {
        "data": "2026-05-10",
        "fornecedor": "Empresa Legada Ltda",
        "cnpj": "",
        "descricao": "Manutenção elevador",
        "valor": 800.0,
        "tipo": "despesa",
        "categoria_sugerida": "Manutenção",
    }
    resultado = _normalizar_transacao(dado, "legado.pdf")

    assert resultado["prestador_destino"] == "Empresa Legada Ltda"
    assert resultado["fonte_pagadora"] == ""
    # Regra determinística de MANUTENÇÃO deve bater
    assert resultado["categoria"] == "Manutenção"

    print("✅ test_normalizar_transacao_legado_fornecedor passou")


def test_regras_deterministicas_prioridade():
    # Regras do YAML devem sobrescrever a sugestão do LLM
    dado = {
        "data": "2026-05-01",
        "fonte_pagadora": "",
        "prestador_destino": "CEMIG Distribuidora",
        "cnpj": "",
        "descricao": "Conta de energia elétrica",
        "numero_documento": "",
        "valor": 420.0,
        "tipo": "despesa",
        "categoria": "Outras Despesas",  # LLM errou a categoria
    }
    resultado = _normalizar_transacao(dado, "cemig.pdf")
    assert resultado["categoria"] == "Energia Elétrica"
    assert resultado["tipo"] == "despesa"

    print("✅ test_regras_deterministicas_prioridade passou")


def test_categorias_validas_nao_vazio():
    cats = _categorias_validas()
    assert len(cats) > 0
    assert "Energia Elétrica" in cats
    assert "Água e Esgoto" in cats
    assert "Manutenção" in cats

    print("✅ test_categorias_validas_nao_vazio passou")


if __name__ == "__main__":
    test_parse_valor()
    test_parse_data()
    test_validar_cnpj()
    test_normalizar_transacao_novos_campos()
    test_normalizar_transacao_data_ausente_marca_suspeito()
    test_normalizar_transacao_legado_fornecedor()
    test_regras_deterministicas_prioridade()
    test_categorias_validas_nao_vazio()
    print("\n✅ Todos os testes de classifier passaram")
