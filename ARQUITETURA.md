# ARQUITETURA.md — Balancete Condominial

## Visão geral

O sistema é uma aplicação local, single-user, estruturada em três camadas com separação clara de responsabilidades. Não há servidor remoto, banco de dados nem autenticação — o estado de cada sessão vive na memória do processo Streamlit.

```
┌─────────────────────────────────────────┐
│           ui/app.py                     │  ← Camada de apresentação
│     (Streamlit — interface web local)   │
└──────────────┬──────────────────────────┘
               │ orquestra
    ┌──────────┼──────────────┐
    ▼          ▼              ▼
┌────────┐ ┌──────────┐ ┌──────────────┐
│extrac- │ │classifi- │ │conciliacao   │  ← Camada de negócio / domínio
│tor.py  │ │er.py     │ │.py           │
└────────┘ └──────────┘ └──────────────┘
    │            │
    │     ┌──────┴──────────┐
    │     │ config/         │
    │     │ categorias.yml  │             ← Configuração / regras externas
    │     └─────────────────┘
    │
    ▼
┌─────────────────────────────┐
│  Ollama (localhost:11434)   │           ← Runtime LLM externo (local)
│  • gemma4:e4b  (texto)      │
│  • qwen3-vl:8b (visão/OCR)  │
└─────────────────────────────┘
```

---

## Princípios arquiteturais

**1. Sem LLM nas camadas de UI e extração**
`extractor.py` não conhece o Ollama. `app.py` não conhece prompts. Isso permite trocar o modelo ou a interface sem reescrever a lógica de extração.

**2. Uma chamada LLM por documento**
O `classifier.py` usa um único prompt unificado que classifica o tipo do documento E extrai os dados em uma só resposta JSON. Isso minimiza latência em hardware com memória de GPU limitada.

**3. Regras determinísticas têm prioridade sobre LLM**
Fornecedores conhecidos (CEMIG, COPASA, INSS etc.) são categorizados via `categorias.yml` sem custo de inferência. O LLM só decide quando nenhuma regra bate.

**4. Estado de sessão centralizado**
Todo o estado entre telas vive em `st.session_state` com estrutura conhecida. Nenhuma função de domínio (`core/`) lê ou escreve no session_state — recebe e retorna dados puros.

**5. Reutilizável como API**
Os módulos de `core/` não têm dependências de Streamlit. O plano é expô-los via `FastAPI` (`POST /balancete`) para integração com o app Flutter sem alterar nenhuma linha de lógica.

---

## Fluxo completo de dados

```
┌─────────────────────────────────────────────────────────────────┐
│ Tela 1 — Configuração                                           │
│  Usuário: competência, saldo inicial, documentos, template      │
└────────────────────────┬────────────────────────────────────────┘
                         │ st.button("Processar")
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│ Para cada documento:                                            │
│                                                                 │
│  extractor.extrair_conteudo_pdf(path)                           │
│    ├── PDF com texto (≥50 chars/pág)                            │
│    │     └── retorna ConteudoPDF.texto                          │
│    └── PDF escaneado                                            │
│          ├── converte páginas → PNG (pdf2image + poppler)       │
│          └── retorna ConteudoPDF.imagens [(num, bytes), ...]    │
│                                                                 │
│  classifier.extrair_de_texto(texto, fonte)   ← PDF com texto   │
│  classifier.extrair_de_imagem(img_b64, fonte) ← imagem/OCR     │
│    ├── [camada 0] aplicar_regras_deterministicas()              │
│    │     └── categorias.yml → (categoria, tipo) ou (None, None) │
│    └── [LLM] 1 chamada ao Ollama com _PROMPT_UNIFICADO          │
│          ├── tipo_documento = "extrato_bancario"                │
│          │     └── _normalizar_movimentacao() → extrato_movs   │
│          └── tipo_documento = comprovante | recibo | nota_fiscal│
│                └── _normalizar_transacao()  → transacoes        │
└────────────────────────┬────────────────────────────────────────┘
                         │ st.session_state.dados_extraidos
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│ Tela 2 — Revisão                                                │
│  st.data_editor — edição linha a linha                          │
│  tab Transações: tipo, valor, categoria, data, fornecedor       │
│  tab Extrato: somente leitura                                   │
└────────────────────────┬────────────────────────────────────────┘
                         │ st.button("Confirmar")
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│ _gerar_resultado()                                              │
│                                                                 │
│  conciliacao.gerar_xlsx(transacoes, extrato_movs, ...)          │
│    ├── separar_suspeitos() → (ok, suspeitos)                    │
│    ├── conciliar(extrato_movs, transacoes)                      │
│    │     └── match por valor (±R$0,05) e data (±3 dias)        │
│    └── gera Workbook com até 6 abas:                            │
│          Resumo / Receitas / Despesas / Extrato /               │
│          Conciliação / ⚠️ Revisar                               │
│                                                                 │
│  OU preencher_template(template_bytes, ...) se houver template  │
└────────────────────────┬────────────────────────────────────────┘
                         │ st.session_state.resultado
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│ Tela 3 — Download                                               │
│  st.download_button → XLSX                                      │
│  st.download_button → ZIP de imagens (se houver PDFs escaneados)│
└─────────────────────────────────────────────────────────────────┘
```

---

## Descrição de cada arquivo

### `ui/app.py` — Interface e orquestrador de telas

**Responsabilidade:** única camada que conhece o Streamlit. Gerencia o fluxo entre as três telas (Configuração → Revisão → Download), acumula estado em `st.session_state` e delega todo processamento para os módulos de `core/`.

**O que faz:**
- Renderiza formulários, upload de arquivos, barra de progresso e log em tempo real
- Chama `extractor`, `classifier` e `conciliacao` na ordem correta
- Exibe o `st.data_editor` para revisão e coleta as edições do usuário
- Reconstrói as transações a partir das edições antes de gerar o XLSX
- Gerencia o cache de imagens em disco (`~/.balancete_cache/imagens/`) para evitar memory leak

**O que NÃO faz:** lógica de negócio, prompts LLM, parsing de PDF, geração de XLSX.

**Funções principais:**

| Função | Descrição |
|---|---|
| `_processar_arquivo()` | Roteador: decide se chama extractor+classifier via texto ou imagem |
| `_tela_revisao()` | Renderiza o data_editor e retorna True quando confirmado |
| `_gerar_resultado()` | Reconstrói transações editadas e chama conciliacao para gerar XLSX |
| `_salvar_imagens_em_disco()` | Persiste PNGs em disco; session_state guarda só os caminhos |
| `_deduplicar_transacoes()` | Remove duplicatas por (data, valor, fornecedor, tipo) |
| `_validar_competencia()` | Valida formato AAAA-MM antes de processar |

---

### `core/extractor.py` — Extração de conteúdo bruto

**Responsabilidade:** recebe um arquivo e devolve conteúdo legível — texto plano para PDFs digitais, ou bytes PNG para PDFs escaneados. Zero conhecimento de LLM ou regras de negócio.

**O que faz:**
- Extrai texto de PDFs via `pdfplumber` (tabelas + texto corrido)
- Conta páginas via `pdfinfo` (rápido) com fallback para `pdfplumber`
- Detecta PDFs escaneados pelo limiar de 50 chars/página
- Converte PDFs escaneados para PNG página a página via `pdf2image` + Poppler
- Codifica imagens em base64 para envio ao modelo de visão

**O que NÃO faz:** chamadas LLM, classificação, geração de XLSX.

**Classes e funções principais:**

| Símbolo | Tipo | Descrição |
|---|---|---|
| `ConteudoPDF` | classe | Container de resultado: `.texto`, `.imagens`, `.tem_texto`, `.total_paginas` |
| `extrair_conteudo_pdf()` | função pública | Entry point — decide texto vs. OCR automaticamente |
| `_extrair_texto()` | interno | Usa pdfplumber com extração de tabelas |
| `_pdf_para_imagens()` | interno | Converte página por página (evita OOM) |
| `carregar_imagem_b64()` | utilitário | Lê arquivo de imagem e retorna base64 |
| `bytes_para_b64()` | utilitário | Converte bytes de PNG para base64 |

---

### `core/classifier.py` — Classificação e extração via LLM

**Responsabilidade:** receber conteúdo bruto (texto ou imagem base64) e devolver transações estruturadas e normalizadas. É a única camada que conversa com o Ollama.

**O que faz:**
- Aplica regras determinísticas do `categorias.yml` antes de qualquer chamada LLM
- Envia um único prompt unificado ao Ollama que classifica o tipo de documento e extrai os dados em uma resposta JSON
- Normaliza o retorno bruto do LLM: converte valores brasileiros ("1.234,56"), valida datas, valida CNPJ com dígitos verificadores
- Marca transações suspeitas (valor zero, data ausente, CNPJ inválido) para revisão
- Exporta `aplicar_regras_deterministicas()` para uso nos testes

**O que NÃO faz:** UI, geração de XLSX, leitura de arquivos.

**Funções principais:**

| Função | Descrição |
|---|---|
| `extrair_de_texto()` | Entry point para PDFs com texto — retorna `(transacoes, extrato_movs)` |
| `extrair_de_imagem()` | Entry point para imagens/OCR — retorna `(transacoes, extrato_movs)` |
| `aplicar_regras_deterministicas()` | Categorização sem LLM via categorias.yml |
| `_llm_texto()` | Wrapper do ollama.chat para o modelo de texto |
| `_llm_visao()` | Wrapper do ollama.chat para o modelo de visão (com imagem) |
| `_parse_valor()` | Converte formatos BR/US/JSON para float (caso crítico) |
| `_validar_cnpj()` | Valida 14 dígitos com verificadores |
| `_normalizar_transacao()` | Monta dict tipado a partir do JSON bruto do LLM |
| `_normalizar_movimentacao()` | Idem para movimentações de extrato |

**Modelos usados:**

| Modelo | Constante | Uso |
|---|---|---|
| `gemma4:e4b` | `TEXTO_MODEL` | PDFs com texto extraível |
| `qwen3-vl:8b` | `VISAO_MODEL` | PDFs escaneados e imagens diretas |

---

### `core/conciliacao.py` — Conciliação e geração de XLSX

**Responsabilidade:** receber listas de transações e movimentações de extrato já normalizadas e produzir o arquivo XLSX final com todas as abas, formatação e conciliação bancária.

**O que faz:**
- Cruza débitos do extrato com despesas do balancete por valor (±R$ 0,05) e data (±3 dias)
- Usa best-match com desempate por menor diferença de data e depois de valor
- Separa transações suspeitas (não exclui dos totais — inclui em aba separada para auditoria)
- Gera Workbook com até 6 abas formatadas
- Preenche templates `.xlsx` personalizados substituindo placeholders `{{...}}`

**O que NÃO faz:** chamadas LLM, leitura de arquivos, UI.

**Funções e abas:**

| Função pública | Descrição |
|---|---|
| `gerar_xlsx()` | Gera XLSX completo do zero com template padrão |
| `preencher_template()` | Preenche template `.xlsx` do usuário + adiciona abas extras |
| `conciliar()` | Best-match entre débitos do extrato e despesas |
| `separar_suspeitos()` | Separa (ok, suspeitos) sem remover suspeitos dos totais |

| Aba gerada | Conteúdo |
|---|---|
| `Resumo` | Saldo inicial, receitas, despesas, saldo final, indicadores de qualidade |
| `Receitas` | Data, histórico, unidade/pagador, categoria, valor, fonte |
| `Despesas` | Data, fornecedor, CNPJ, histórico, categoria, valor, fonte |
| `Extrato (Referência)` | Movimentações brutas do extrato para conferência |
| `Conciliação` | Semáforo 🟢🔴🔵 de pares extrato × balancete |
| `⚠️ Revisar` | Transações com baixa confiança (informativo, não afeta totais) |

---

### `config/categorias.yml` — Regras determinísticas de categorização

**Responsabilidade:** lista de regras regex que mapeiam fornecedor/descrição para categoria e tipo (despesa/receita) sem nenhuma chamada LLM.

**Estrutura:**

```yaml
regras:
  - padrao: "CEMIG|CELPE|..."   # regex case-insensitive
    categoria: "Energia Elétrica"
    tipo: despesa
```

**Como é usado:** `classifier._carregar_regras()` lê e faz cache na primeira chamada. `aplicar_regras_deterministicas()` itera as regras na ordem — a primeira que bater ganha.

**Critérios de qualidade dos padrões:**
- Padrões curtos usam `\b` (word boundary) para evitar falsos positivos
- Nomes de empresas específicas (CEMIG, COPASA) não precisam de boundary — são suficientemente únicos
- Ordem importa: regras mais específicas devem vir antes das genéricas

---

### `tests/test_classifier.py` — Testes unitários do classifier

Cobre `_parse_valor()` e `_validar_cnpj()` com casos-limite:

- Formatos de valor: JSON (`1234.56`), BR sem milhar (`1234,56`), BR com milhar (`1.234,56`), US com milhar (`1,234.56`), com prefixo `R$`
- CNPJ: dígitos válidos, inválidos, formatado com pontuação, quantidade errada

---

### `tests/test_categorias.py` — Testes das regras determinísticas

Verifica falsos positivos e verdadeiros positivos das regras do `categorias.yml`:

- Casos que devem bater: CEMIG → Energia Elétrica, COPASA → Água e Esgoto, etc.
- Casos que NÃO devem bater: "PORTARIA VIRTUAL" não é Pessoal, "MULTA CONTRATUAL" não é receita

---

### `tests/test_conciliacao.py` — Testes da conciliação bancária

Verifica o algoritmo de best-match com cenários de:

- Match exato (data e valor idênticos)
- Match por tolerância (data ±3 dias, valor ±R$0,05)
- Itens sem par no extrato e no balancete
- Prioridade: match com menor diferença de data ganha

---

### `scripts/check_env.py` — Verificação de pré-requisitos

Script de diagnóstico executado antes da primeira execução ou após instalação. Verifica Python, Ollama, modelos, Poppler e dependências Python. Imprime ✅/❌ para cada item.

---

## Decisões técnicas relevantes

### Por que Ollama e não API OpenAI/Anthropic?

O requisito central é **100% offline**. Dados financeiros de condomínio contêm CPFs, CNPJs, valores e nomes de moradores — não podem sair da máquina do usuário.

### Por que Streamlit e não FastAPI + React?

Streamlit permite UI funcional em um único arquivo Python, sem Node.js, sem build step, sem CORS. O público-alvo (síndico ou administradora) não precisa de instalação além do `pip install`. A FastAPI virá na integração com o Flutter.

### Por que pdfplumber e não PyMuPDF?

`pdfplumber` é superior para extração de tabelas, que é o caso mais comum em extratos bancários. `PyMuPDF` fica como fallback para PDFs com estrutura incomum.

### Por que não LangChain?

O pipeline tem exatamente uma chamada LLM por documento, com prompt fixo e parsing JSON determinístico. LangChain adicionaria dependência e complexidade sem benefício real para esse caso de uso.

### Por que imagens em disco e não em session_state?

PDFs escaneados de 30 páginas a 150 DPI geram ~50–100 MB de bytes PNG. O `st.session_state` do Streamlit vive na memória do processo Python e nunca é coletado pelo GC enquanto a sessão estiver ativa. Com múltiplos usuários ou sessões longas, isso causa OOM. A solução é persistir em `~/.balancete_cache/imagens/` e guardar apenas caminhos no estado.

---

## Roadmap de integração Flutter

O próximo passo planejado é expor os módulos de `core/` via FastAPI:

```
POST /balancete
  body: multipart (arquivos + competência + saldo_inicial)
  response: { xlsx_b64, transacoes, extrato_movs, suspeitos }
```

Nenhum arquivo de `core/` precisará ser alterado — apenas um novo `api/main.py` será criado como adaptador.
