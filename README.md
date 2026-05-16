# 🏢 Balancete Condominial

> Ferramenta local, 100% offline, para geração automatizada de balancetes de condomínio a partir de documentos financeiros brutos — extratos bancários, comprovantes, recibos e notas fiscais.

**Nenhum dado sai da máquina do usuário.** Todo o processamento de IA ocorre via [Ollama](https://ollama.com), rodando localmente.

---

## Índice

- [Visão geral](#visão-geral)
- [Funcionalidades](#funcionalidades)
- [Pré-requisitos](#pré-requisitos)
- [Instalação rápida](#instalação-rápida)
- [Como usar](#como-usar)
- [Estrutura do projeto](#estrutura-do-projeto)
- [Documentação](#documentação)
- [Contribuindo](#contribuindo)
- [Licença](#licença)

---

## Visão geral

O Balancete Condominial recebe documentos financeiros brutos (PDF ou imagem) e automatiza o processo que hoje é feito manualmente por síndicos e administradoras:

```
Documentos (PDF/imagem)
        │
        ▼
  Extração de conteúdo
  (texto ou OCR via visão)
        │
        ▼
  Classificação + Extração
  (LLM local — 1 chamada por doc)
        │
        ▼
  Revisão pelo síndico
  (tela de edição antes de exportar)
        │
        ▼
  Balancete XLSX
  (Resumo / Receitas / Despesas /
   Extrato / Conciliação / Revisão)
```

---

## Funcionalidades

- **Upload múltiplo** — PDFs e imagens (PNG, JPG) em lote
- **Detecção automática** — PDF com texto vs. escaneado (OCR via visão)
- **Classificação inteligente** — tipo de documento e categoria em 1 chamada LLM
- **Regras determinísticas** — CEMIG, COPASA, INSS etc. categorizados sem LLM
- **Tela de revisão** — edição manual antes de gerar o XLSX
- **Conciliação bancária** — cruza extrato com despesas do balancete
- **XLSX rico** — até 6 abas com formatação, totais e semáforo de conciliação
- **Template personalizado** — suporte a `.xlsx` próprio da administradora
- **Export de imagens** — ZIP com PNGs das páginas convertidas (reutilizáveis)
- **100% offline** — zero API keys, zero envio de dados

---

## Pré-requisitos

| Requisito | Versão mínima | Observação |
|---|---|---|
| Python | 3.11+ | [python.org](https://python.org/downloads) |
| Ollama | qualquer | [ollama.com/download](https://ollama.com/download) |
| Poppler | qualquer | Para conversão de PDFs escaneados |
| RAM | 16 GB | 32 GB recomendado para melhor performance |
| Disco | ~15 GB livres | Para os modelos de IA |

> **Hardware testado:** Mac / Windows com 32 GB RAM, GPU 4 GB VRAM.
> Latência estimada: 2–5 min por balancete com ~100 transações.

---

## Instalação rápida

Consulte o **[SETUP.md](docs/SETUP.md)** para o guia completo por sistema operacional.

```bash
# 1. Clone o repositório
git clone https://github.com/seu-usuario/balancete-condominial.git
cd balancete-condominial

# 2. Crie e ative o ambiente virtual
python -m venv venv
source venv/bin/activate        # Linux/Mac
# venv\Scripts\activate         # Windows

# 3. Instale as dependências
pip install -r requirements.txt

# 4. Baixe os modelos de IA (feito uma única vez, ~13 GB)
ollama pull gemma4:e4b
ollama pull qwen3-vl:8b

# 5. Rode o app
streamlit run ui/app.py
```

O browser abre automaticamente em `http://localhost:8501`.

---

## Como usar

1. Informe a **competência** no formato `AAAA-MM` (ex: `2026-05`) e o **saldo inicial**
2. Faça upload dos documentos — extratos, comprovantes, recibos, notas fiscais
3. Aguarde o processamento (barra de progresso + log em tempo real)
4. **Revise as transações** extraídas — edite qualquer campo antes de exportar
5. Clique em **Confirmar e gerar XLSX**
6. Baixe o balancete `.xlsx` e, se houver PDFs escaneados, o `.zip` com as imagens

### Tipos de documento reconhecidos

| Tipo | O que acontece |
|---|---|
| Extrato bancário | Vai para a aba **Extrato (Referência)** — usado na conciliação, não entra nos totais |
| Comprovante de pagamento | Classificado como despesa no balancete |
| Recibo | Classificado como despesa no balancete |
| Nota fiscal | Classificado como despesa no balancete |

---

## Estrutura do projeto

```
balancete-condominial/
├── ui/
│   └── app.py                  # Interface Streamlit (orquestrador de telas)
│
├── core/
│   ├── extractor.py            # Extração de conteúdo de PDF/imagem (sem LLM)
│   ├── classifier.py           # Classificação e extração via LLM (1 chamada/doc)
│   └── conciliacao.py          # Conciliação bancária e geração do XLSX
│
├── config/
│   └── categorias.yml          # Regras determinísticas de categorização (sem LLM)
│
├── tests/
│   ├── test_classifier.py      # Testes unitários do classifier
│   ├── test_categorias.py      # Testes das regras determinísticas
│   └── test_conciliacao.py     # Testes da conciliação bancária
│
├── docs/
│   ├── SETUP.md                # Guia de instalação (Windows, Mac, Linux)
│   ├── ARQUITETURA.md          # Arquitetura de software e responsabilidades
│   └── REGRAS_DE_NEGOCIO.md    # Regras de negócio do domínio condominial
│
├── scripts/
│   └── check_env.py            # Verifica pré-requisitos antes de rodar
│
├── .github/
│   └── ISSUE_TEMPLATE/
│       ├── bug_report.md
│       └── feature_request.md
│
├── .gitignore
├── requirements.txt
└── README.md                   # Este arquivo
```

---

## Documentação

| Arquivo | Conteúdo |
|---|---|
| [docs/SETUP.md](docs/SETUP.md) | Instalação passo a passo para Windows, Mac e Linux |
| [docs/ARQUITETURA.md](docs/ARQUITETURA.md) | Arquitetura do sistema, fluxo de dados e responsabilidades |
| [docs/REGRAS_DE_NEGOCIO.md](docs/REGRAS_DE_NEGOCIO.md) | Regras do domínio condominial — categorias, tolerâncias, critérios |

---

## Contribuindo

1. Fork o repositório
2. Crie uma branch descritiva: `git checkout -b fix/parse-valor-brasileiro`
3. Faça suas alterações com testes
4. Rode os testes: `python -m pytest tests/`
5. Abra um Pull Request descrevendo o problema e a solução

> Convenção de branches: `fix/` para correções, `feat/` para funcionalidades, `docs/` para documentação.

---

## Licença

MIT — veja [LICENSE](LICENSE) para detalhes.
