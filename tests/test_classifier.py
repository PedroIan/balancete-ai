"""
Testes unitários para core/classifier.py
Execute com: python tests/test_classifier.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.classifier import _parse_valor, _validar_cnpj


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


if __name__ == "__main__":
    test_parse_valor()
    test_validar_cnpj()
    print("\n✅ Todos os testes de classifier passaram")
