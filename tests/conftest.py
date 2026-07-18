"""
conftest.py — configuração global do pytest.
Garante que o pacote raiz está no sys.path e que `ollama` (não instalado no
ambiente de testes) não bloqueia a importação de core.classifier.
"""
import sys
import types
from pathlib import Path

# Raiz do projeto no caminho de importação
_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# Stub de ollama — substitui o módulo real antes de qualquer import dos testes
if "ollama" not in sys.modules:
    _stub = types.ModuleType("ollama")
    _stub.chat = lambda **kw: {"message": {"content": "{}"}}
    sys.modules["ollama"] = _stub
