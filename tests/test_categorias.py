"""
Testes das regras determinísticas em config/categorias.yml
Execute com: python tests/test_categorias.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.classifier import aplicar_regras_deterministicas


def test_regras():
    # Verdadeiros positivos
    assert aplicar_regras_deterministicas("CEMIG", "CONTA DE LUZ") == ("Energia Elétrica", "despesa")
    assert aplicar_regras_deterministicas("COPASA", "AGUA") == ("Água e Esgoto", "despesa")
    assert aplicar_regras_deterministicas(None, "FOLHA DE PAGAMENTO MARÇO") == ("Pessoal e Encargos", "despesa")
    assert aplicar_regras_deterministicas(None, "INSS COMPETÊNCIA 03/2026") == ("Pessoal e Encargos", "despesa")
    assert aplicar_regras_deterministicas(None, "TAXA DE MUDANÇA APTO 301") == ("Taxa de Mudança", "receita")
    assert aplicar_regras_deterministicas(None, "MULTA CONDOMINIAL APTO 102") == ("Multas e Juros", "receita")

    # Falsos positivos que NÃO devem bater
    assert aplicar_regras_deterministicas(None, "PORTARIA VIRTUAL")[0] != "Pessoal e Encargos"
    assert aplicar_regras_deterministicas(None, "MULTA CONTRATUAL CONSTRUTORA")[0] != "Multas e Juros"
    assert aplicar_regras_deterministicas(None, "MUDANÇA DE LAYOUT HALL")[0] != "Taxa de Mudança"

    print("✅ test_regras passou")


if __name__ == "__main__":
    test_regras()
    print("\n✅ Todos os testes de categorias passaram")
