"""
check_env.py
Verifica todos os pré-requisitos antes de rodar o app.
Execute com: python scripts/check_env.py
"""

import importlib.util
import shutil
import subprocess
import sys
import urllib.request

OK   = "✅"
ERR  = "❌"
WARN = "⚠️ "

erros = 0

# 1. Python
versao = sys.version_info
if versao >= (3, 11):
    print(f"{OK} Python {versao.major}.{versao.minor}.{versao.micro}")
else:
    print(f"{ERR} Python {versao.major}.{versao.minor} — requer 3.11+")
    erros += 1

# 2. Ollama rodando
try:
    urllib.request.urlopen("http://localhost:11434", timeout=3)
    print(f"{OK} Ollama rodando em localhost:11434")
except Exception:
    print(f"{ERR} Ollama não está rodando — inicie o servidor Ollama")
    erros += 1

# 3. Modelos disponíveis
try:
    import ollama
    modelos_info = ollama.list()
    modelos = [m["name"] for m in modelos_info.get("models", [])]
    for modelo in ["gemma4:e4b", "qwen3-vl:8b"]:
        if any(modelo in m for m in modelos):
            print(f"{OK} Modelo {modelo} disponível")
        else:
            print(f"{ERR} Modelo {modelo} não encontrado — execute: ollama pull {modelo}")
            erros += 1
except Exception as e:
    print(f"{WARN} Não foi possível verificar modelos: {e}")

# 4. Poppler
if shutil.which("pdfinfo"):
    print(f"{OK} Poppler (pdfinfo) disponível")
else:
    print(f"{ERR} Poppler não encontrado — veja SETUP.md")
    erros += 1

# 5. Dependências Python
deps = {
    "streamlit": "streamlit",
    "ollama": "ollama",
    "pdfplumber": "pdfplumber",
    "pdf2image": "pdf2image",
    "openpyxl": "openpyxl",
    "pandas": "pandas",
    "pyyaml": "yaml",
    "pydantic": "pydantic",
    "Pillow": "PIL",
}
for nome_pip, nome_import in deps.items():
    if importlib.util.find_spec(nome_import):
        print(f"{OK} {nome_pip}")
    else:
        print(f"{ERR} {nome_pip} não instalado — pip install -r requirements.txt")
        erros += 1

print()
if erros == 0:
    print("Ambiente pronto. Execute: streamlit run ui/app.py")
else:
    print(f"{erros} problema(s) encontrado(s). Resolva antes de continuar.")
    sys.exit(1)
