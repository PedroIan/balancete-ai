"""
Testes unitários para core/classifier.py
Execute com: python tests/test_classifier.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import json

from core.classifier import (
    _PROMPT_UNIFICADO,
    CATEGORIAS_DESPESA,
    CATEGORIAS_RECEITA,
    _dividir_em_chunks,
    _parse_json_llm,
    _parse_valor,
    _processar_resposta,
    _validar_cnpj,
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


def test_prompt_unificado():
    # Tipos de documento esperados pelo fluxo, incluindo cupom fiscal (térmica)
    for tipo in ("extrato_bancario", "comprovante", "recibo", "nota_fiscal", "cupom_fiscal", "outro"):
        assert f'"{tipo}"' in _PROMPT_UNIFICADO, f"prompt sem tipo {tipo}"

    # Lista fechada de categorias presente no prompt
    for cat in CATEGORIAS_DESPESA + CATEGORIAS_RECEITA:
        assert cat in _PROMPT_UNIFICADO, f"prompt sem categoria {cat}"

    print("✅ test_prompt_unificado passou")


def test_dividir_em_chunks():
    assert _dividir_em_chunks("abc", 100) == ["abc"]

    linhas = "\n".join(f"linha {i}" for i in range(100))
    chunks = _dividir_em_chunks(linhas, 200)
    assert len(chunks) > 1
    assert all(len(c) <= 200 for c in chunks)
    # Nenhuma linha cortada ao meio e nada perdido
    assert "\n".join(chunks).splitlines() == linhas.splitlines()

    print("✅ test_dividir_em_chunks passou")


def test_processar_resposta():
    # Cupom fiscal gera transação (não é descartado como "outro")
    resposta = json.dumps({
        "tipo_documento": "cupom_fiscal",
        "transacoes": [{
            "data": "2026-05-10",
            "fornecedor": "SUPERMERCADO ABC",
            "cnpj": None,
            "descricao": "Material de limpeza",
            "valor": 87.50,
            "tipo": "despesa",
            "categoria_sugerida": "Material de Consumo",
        }],
    })
    txs, movs, aviso = _processar_resposta(resposta, "cupom.jpg")
    assert len(txs) == 1 and not movs and aviso is None
    assert txs[0]["categoria"] == "Material de Consumo"

    # Categoria inventada pelo LLM cai no fallback da lista fechada
    resposta = json.dumps({
        "tipo_documento": "comprovante",
        "transacoes": [{
            "data": "2026-05-10",
            "fornecedor": "QUALQUER",
            "descricao": "Serviço avulso",
            "valor": 10.0,
            "tipo": "despesa",
            "categoria_sugerida": "Luz e Energia",
        }],
    })
    txs, _, _ = _processar_resposta(resposta, "doc.pdf")
    assert txs[0]["categoria"] == "Outras Despesas"

    # JSON inválido → aviso, nunca descarte silencioso
    txs, movs, aviso = _processar_resposta("não sei o que fazer com isso", "doc.pdf")
    assert txs == [] and movs == [] and aviso is not None

    # Tipo "outro" → aviso
    txs, movs, aviso = _processar_resposta('{"tipo_documento": "outro", "transacoes": []}', "doc.pdf")
    assert txs == [] and movs == [] and aviso is not None

    print("✅ test_processar_resposta passou")


def test_parse_json_llm():
    assert _parse_json_llm('{"a": 1}') == {"a": 1}
    assert _parse_json_llm('```json\n{"a": 1}\n```') == {"a": 1}
    assert _parse_json_llm('Claro! Aqui está: {"a": 1}') == {"a": 1}
    assert _parse_json_llm("nenhum json aqui") is None
    assert _parse_json_llm("[1, 2, 3]") is None  # lista não é o schema esperado

    print("✅ test_parse_json_llm passou")


if __name__ == "__main__":
    test_parse_valor()
    test_validar_cnpj()
    test_prompt_unificado()
    test_dividir_em_chunks()
    test_processar_resposta()
    test_parse_json_llm()
    print("\n✅ Todos os testes de classifier passaram")
