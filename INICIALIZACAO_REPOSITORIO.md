# Guia de Inicialização do Repositório

Passo a passo completo para um desenvolvedor criar o repositório do zero, estruturar as pastas, configurar o ambiente e fazer o primeiro commit. Siga na ordem exata.

---

## Pré-requisitos

Antes de começar, certifique-se de ter instalado localmente:

- Git (`git --version`)
- Python 3.11+ (`python --version`)
- Conta no GitHub com acesso para criar repositórios
- Ollama instalado e rodando (`http://localhost:11434`)
- Poppler instalado (`pdfinfo --version`)

---

## Passo 1 — Criar o repositório no GitHub

1. Acesse **github.com/new**
2. Preencha:
   - **Repository name:** `balancete-condominial`
   - **Description:** `Gerador de balancetes condominiais com IA local (Ollama) — 100% offline`
   - **Visibility:** Private *(dados financeiros — não deixe público)*
   - **Add a README file:** ❌ desmarcado *(vamos criar manualmente)*
   - **Add .gitignore:** ❌ desmarcado *(vamos criar manualmente)*
   - **Choose a license:** MIT
3. Clique em **Create repository**
4. Copie a URL SSH ou HTTPS do repositório criado

---

## Passo 2 — Clonar e criar a estrutura de pastas

```bash
# Clone o repositório vazio
git clone git@github.com:seu-usuario/balancete-condominial.git
cd balancete-condominial

# Crie toda a estrutura de diretórios de uma vez
mkdir -p ui core config tests docs scripts .github/ISSUE_TEMPLATE
```

A estrutura final será:

```
balancete-condominial/
├── ui/                        # Interface Streamlit
├── core/                      # Lógica de negócio (sem UI)
├── config/                    # Configurações externas (YAML)
├── tests/                     # Testes unitários
├── docs/                      # Documentação do projeto
├── scripts/                   # Utilitários de desenvolvimento
└── .github/
    └── ISSUE_TEMPLATE/        # Templates de issues do GitHub
```

---

## Passo 3 — Criar o .gitignore

```bash
cat > .gitignore << 'EOF'
# Python
__pycache__/
*.py[cod]
*.pyo
*.pyd
.Python
*.egg
*.egg-info/
dist/
build/
.eggs/

# Ambiente virtual
venv/
.venv/
env/
.env/

# Streamlit
.streamlit/

# Cache local da aplicação (imagens convertidas de PDFs escaneados)
.balancete_cache/

# Arquivos de saída gerados
*.xlsx
*.zip

# IDEs
.vscode/
.idea/
*.swp
*.swo

# macOS
.DS_Store
.AppleDouble

# Windows
Thumbs.db
desktop.ini

# Logs
*.log
logs/

# Arquivos de ambiente
.env
.env.local

# Documentos de teste (nunca versionar dados reais)
tests/fixtures/dados_reais/
tests/fixtures/*.pdf
tests/fixtures/*.png
tests/fixtures/*.jpg
EOF
```

> ⚠️ **Importante:** nunca versione PDFs reais, imagens de documentos ou qualquer arquivo com dados financeiros de moradores. Use apenas fixtures sintéticas nos testes.

---

## Passo 4 — Criar o requirements.txt

```bash
cat > requirements.txt << 'EOF'
# Interface
streamlit>=1.35.0

# LLM local
ollama>=0.2.0

# Extração de PDF
pdfplumber>=0.11.0
pdf2image>=1.17.0

# Geração de XLSX
openpyxl>=3.1.0

# Processamento de dados
pandas>=2.0.0

# Configuração externa
pyyaml>=6.0

# Validação
pydantic>=2.0.0

# Imagens
Pillow>=10.0.0
EOF
```

Instale imediatamente para validar:

```bash
python -m venv venv

# Mac/Linux
source venv/bin/activate

# Windows
venv\Scripts\activate

pip install -r requirements.txt
```

---

## Passo 5 — Copiar os arquivos do projeto

Copie os arquivos-fonte para as pastas corretas:

```bash
# Arquivos principais
cp app.py       ui/app.py
cp extractor.py core/extractor.py
cp classifier.py core/classifier.py
cp conciliacao.py core/conciliacao.py
cp categorias.yml config/categorias.yml
```

Se você está começando do zero (sem os arquivos existentes), crie os arquivos vazios com o docstring de cada módulo agora e implemente depois:

```bash
# Cria arquivos de placeholder
touch ui/app.py
touch core/extractor.py
touch core/classifier.py
touch core/conciliacao.py
touch config/categorias.yml
```

---

## Passo 6 — Criar os arquivos `__init__.py`

O Python precisa desses arquivos para reconhecer as pastas como módulos:

```bash
touch core/__init__.py
touch ui/__init__.py
touch tests/__init__.py
```

---

## Passo 7 — Criar o script de verificação de ambiente

```bash
cat > scripts/check_env.py << 'EOF'
"""
check_env.py
Verifica todos os pré-requisitos antes de rodar o app.
Execute com: python scripts/check_env.py
"""

import importlib
import shutil
import subprocess
import sys

OK  = "✅"
ERR = "❌"
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
    import urllib.request
    urllib.request.urlopen("http://localhost:11434", timeout=3)
    print(f"{OK} Ollama rodando em localhost:11434")
except Exception:
    print(f"{ERR} Ollama não está rodando — inicie o servidor Ollama")
    erros += 1

# 3. Modelos disponíveis
try:
    import ollama
    modelos = [m["name"] for m in ollama.list()["models"]]
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
    print(f"{ERR} Poppler não encontrado — veja docs/SETUP.md")
    erros += 1

# 5. Dependências Python
deps = [
    "streamlit", "ollama", "pdfplumber", "pdf2image",
    "openpyxl", "pandas", "yaml", "pydantic", "PIL",
]
for dep in deps:
    mod = "yaml" if dep == "yaml" else dep
    if importlib.util.find_spec(mod):
        print(f"{OK} {dep}")
    else:
        print(f"{ERR} {dep} não instalado — pip install -r requirements.txt")
        erros += 1

print()
if erros == 0:
    print("Ambiente pronto. Execute: streamlit run ui/app.py")
else:
    print(f"{erros} problema(s) encontrado(s). Resolva antes de continuar.")
    sys.exit(1)
EOF
```

Teste:

```bash
python scripts/check_env.py
```

---

## Passo 8 — Criar os arquivos de documentação

Copie os documentos já criados:

```bash
# Se você tem os arquivos do projeto de referência:
cp README.md README.md                          # já está na raiz
cp docs/SETUP.md docs/SETUP.md                 # já está em docs/
cp docs/ARQUITETURA.md docs/ARQUITETURA.md     # já está em docs/
cp docs/REGRAS_DE_NEGOCIO.md docs/REGRAS_DE_NEGOCIO.md
```

---

## Passo 9 — Criar os arquivos de teste (esqueleto)

```bash
cat > tests/test_classifier.py << 'EOF'
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
EOF

cat > tests/test_categorias.py << 'EOF'
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
EOF

cat > tests/test_conciliacao.py << 'EOF'
"""
Testes da conciliação bancária em core/conciliacao.py
Execute com: python tests/test_conciliacao.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.conciliacao import conciliar


def test_conciliacao_basica():
    extrato = [
        {"data": "2026-05-10", "descricao": "PAG CEMIG", "valor": 450.00, "tipo": "debito", "saldo": None, "fonte": "extrato"},
        {"data": "2026-05-12", "descricao": "PAG COPASA", "valor": 120.00, "tipo": "debito", "saldo": None, "fonte": "extrato"},
        {"data": "2026-05-15", "descricao": "TRANSF PIX", "valor": 800.00, "tipo": "debito", "saldo": None, "fonte": "extrato"},
    ]
    transacoes = [
        {"data": "2026-05-10", "descricao": "Energia elétrica", "fornecedor": "CEMIG", "valor": 450.00, "tipo": "despesa", "categoria": "Energia", "cnpj": "", "fonte": "nf1.pdf"},
        {"data": "2026-05-11", "descricao": "Água e esgoto", "fornecedor": "COPASA", "valor": 120.00, "tipo": "despesa", "categoria": "Água", "cnpj": "", "fonte": "nf2.pdf"},
    ]

    pares, ext_sem, tx_sem = conciliar(extrato, transacoes)

    assert len(pares) == 2, f"Esperava 2 pares, obteve {len(pares)}"
    assert len(ext_sem) == 1
    assert ext_sem[0]["valor"] == 800.00
    assert len(tx_sem) == 0

    print("✅ test_conciliacao_basica passou")


if __name__ == "__main__":
    test_conciliacao_basica()
    print("\n✅ Todos os testes de conciliação passaram")
EOF
```

---

## Passo 10 — Criar os templates de issue do GitHub

```bash
cat > .github/ISSUE_TEMPLATE/bug_report.md << 'EOF'
---
name: Bug report
about: Reporte um problema no sistema
title: '[BUG] '
labels: bug
assignees: ''
---

## Descrição do problema

Descreva o que aconteceu e o que você esperava que acontecesse.

## Passos para reproduzir

1. ...
2. ...
3. ...

## Ambiente

- OS: [ex: Windows 11, macOS 14, Ubuntu 22.04]
- Python: [ex: 3.11.5]
- Ollama: [ex: 0.2.1]
- Modelos: [ex: gemma4:e4b, qwen3-vl:8b]

## Tipo de documento que causou o problema

- [ ] PDF com texto
- [ ] PDF escaneado
- [ ] Imagem direta (PNG/JPG)

## Log de erro

```
Cole aqui o erro completo do terminal
```

## Informações adicionais

Qualquer contexto adicional sobre o problema.
EOF

cat > .github/ISSUE_TEMPLATE/feature_request.md << 'EOF'
---
name: Feature request
about: Sugira uma melhoria ou nova funcionalidade
title: '[FEAT] '
labels: enhancement
assignees: ''
---

## Problema que essa feature resolveria

Descreva o problema ou limitação atual.

## Solução proposta

Descreva o comportamento esperado.

## Alternativas consideradas

Descreva outras abordagens que você considerou.

## Contexto adicional

Adicione qualquer contexto, mockup ou exemplo relevante.
EOF
```

---

## Passo 11 — Ajustar os imports para a nova estrutura de pastas

Após mover os arquivos para as subpastas, os imports precisam ser atualizados em `ui/app.py`:

```python
# ANTES (quando tudo estava na raiz):
from classifier import (...)
from conciliacao import gerar_xlsx, preencher_template
from extractor import ConteudoPDF, bytes_para_b64, carregar_imagem_b64, extrair_conteudo_pdf

# DEPOIS (com a estrutura de pastas):
from core.classifier import (...)
from core.conciliacao import gerar_xlsx, preencher_template
from core.extractor import ConteudoPDF, bytes_para_b64, carregar_imagem_b64, extrair_conteudo_pdf
```

Faça o mesmo em `core/classifier.py` para o `categorias.yml`:

```python
# ANTES:
yml_path = Path(__file__).parent / "categorias.yml"

# DEPOIS:
yml_path = Path(__file__).parent.parent / "config" / "categorias.yml"
```

---

## Passo 12 — Primeiro commit

```bash
# Verifica o que será commitado
git status

# Adiciona tudo
git add .

# Commit inicial
git commit -m "feat: estrutura inicial do projeto

- Organização por pastas: ui/, core/, config/, tests/, docs/, scripts/
- Módulos: extractor, classifier, conciliacao
- Regras determinísticas: config/categorias.yml
- Documentação: README, SETUP, ARQUITETURA, REGRAS_DE_NEGOCIO
- Testes: test_classifier, test_categorias, test_conciliacao
- Scripts: check_env.py
- .gitignore configurado para não versionar dados reais"

# Envia para o GitHub
git push origin main
```

---

## Passo 13 — Configurar proteção de branch (recomendado)

No GitHub, vá em **Settings → Branches → Add rule**:

- **Branch name pattern:** `main`
- ✅ Require a pull request before merging
- ✅ Require approvals: 1
- ✅ Require status checks to pass before merging
- ✅ Do not allow bypassing the above settings

Isso garante que nenhuma alteração vai direto para `main` sem revisão.

---

## Passo 14 — Validação final

Execute todos os testes para confirmar que tudo está funcionando:

```bash
# Verifica o ambiente
python scripts/check_env.py

# Roda os testes (sem precisar do Ollama)
python tests/test_classifier.py
python tests/test_categorias.py
python tests/test_conciliacao.py

# Verifica sintaxe de todos os módulos
python -m py_compile ui/app.py
python -m py_compile core/extractor.py
python -m py_compile core/classifier.py
python -m py_compile core/conciliacao.py

# Sobe o app
streamlit run ui/app.py
```

---

## Estrutura final do repositório

```
balancete-condominial/
│
├── ui/
│   ├── __init__.py
│   └── app.py                  # Interface Streamlit — orquestrador de telas
│
├── core/
│   ├── __init__.py
│   ├── extractor.py            # Extração de conteúdo de PDF/imagem (sem LLM)
│   ├── classifier.py           # Classificação e extração via LLM (1 chamada/doc)
│   └── conciliacao.py          # Conciliação bancária e geração do XLSX
│
├── config/
│   └── categorias.yml          # Regras determinísticas — fornecedor → categoria
│
├── tests/
│   ├── __init__.py
│   ├── test_classifier.py      # Testes de _parse_valor e _validar_cnpj
│   ├── test_categorias.py      # Testes das regras do categorias.yml
│   └── test_conciliacao.py     # Testes do algoritmo de conciliação
│
├── docs/
│   ├── SETUP.md                # Guia de instalação (Windows, Mac, Linux)
│   ├── ARQUITETURA.md          # Arquitetura, fluxo de dados, decisões técnicas
│   └── REGRAS_DE_NEGOCIO.md    # Regras do domínio condominial
│
├── scripts/
│   └── check_env.py            # Diagnóstico de pré-requisitos
│
├── .github/
│   └── ISSUE_TEMPLATE/
│       ├── bug_report.md
│       └── feature_request.md
│
├── .gitignore
├── requirements.txt
└── README.md
```

---

## Convenção de branches e commits

### Branches

| Prefixo | Uso | Exemplo |
|---|---|---|
| `feat/` | Nova funcionalidade | `feat/validacao-cnpj` |
| `fix/` | Correção de bug | `fix/parse-valor-brasileiro` |
| `docs/` | Documentação | `docs/atualiza-setup-linux` |
| `refactor/` | Refatoração sem nova feature | `refactor/conciliacao-best-match` |
| `test/` | Adição ou correção de testes | `test/cobertura-classifier` |
| `chore/` | Tarefas de manutenção | `chore/atualiza-requirements` |

### Commits (Conventional Commits)

```
tipo(escopo): descrição curta em imperativo

[corpo opcional — explica o porquê, não o o quê]

[rodapé opcional — referências a issues: Closes #42]
```

Exemplos:

```
feat(classifier): adiciona suporte a valores em formato US com milhar

fix(conciliacao): corrige first-match por best-match na conciliação

docs(setup): adiciona instruções para Linux Ubuntu/Debian

test(classifier): adiciona casos de CNPJ com zeros à esquerda
```
