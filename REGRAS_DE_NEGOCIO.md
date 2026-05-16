# REGRAS_DE_NEGOCIO.md — Balancete Condominial

Este documento registra as regras do domínio financeiro condominial que guiam o comportamento do sistema. Serve como referência para qualquer desenvolvedor que precise entender **por que** o sistema se comporta de determinada forma, além de como.

---

## 1. Tipos de documento e como são tratados

### 1.1 Extrato bancário

**Definição:** listagem de movimentações de uma conta bancária em um período (geralmente mensal). Inclui créditos (entradas) e débitos (saídas) com data, descrição e saldo.

**Regra:** movimentações de extrato bancário **não entram diretamente no balancete** como receitas ou despesas. Elas vão para a aba **"Extrato (Referência)"** e são usadas exclusivamente na conciliação bancária.

**Justificativa:** o extrato mostra o que aconteceu na conta do banco. O balancete mostra o que foi aprovado/reconhecido pela gestão. São visões complementares — confundi-las gera dupla contagem.

**Campos extraídos:**

| Campo | Tipo | Obrigatório |
|---|---|---|
| `data` | AAAA-MM-DD | sim |
| `descricao` | texto | sim |
| `valor` | float positivo | sim |
| `tipo` | `"credito"` ou `"debito"` | sim |
| `saldo` | float positivo | não |

### 1.2 Comprovante de pagamento

**Definição:** documento que comprova um pagamento efetuado (boleto quitado, comprovante de PIX, TED, DOC).

**Regra:** classificado como **despesa** por padrão. Só é receita se o documento evidenciar claramente um recebimento pelo condomínio (ex: comprovante de PIX recebido de um morador).

### 1.3 Recibo

**Definição:** documento emitido pelo recebedor confirmando o recebimento de um valor.

**Regra:** classificado como **despesa** por padrão (o condomínio pagou e o prestador emitiu recibo). Exceção: recibos de taxas condominiais recebidas são receita.

### 1.4 Nota fiscal

**Definição:** NF-e, NFC-e, NFS-e, DANFE ou cupom fiscal emitido por um fornecedor.

**Regra:** sempre classificada como **despesa**. O valor relevante é o `valor_total` da nota, não parcelas ou deduções.

---

## 2. Categorias e critérios de classificação

### 2.1 Categorias de despesa

| Categoria | Critérios | Exemplos |
|---|---|---|
| **Pessoal e Encargos** | Pagamentos a funcionários e obrigações trabalhistas/previdenciárias | Folha de pagamento, FGTS, INSS, GPS, DARF, rescisão, férias, 13º, vale-transporte, vale-alimentação |
| **Manutenção** | Serviços e materiais para conservação das áreas comuns | Reparo de elevador, conserto de bomba, pintura, reforma, instalação elétrica/hidráulica |
| **Limpeza** | Serviços de higienização e dedetização | Faxina, zeladoria, dedetização, desinfecção, descupinização |
| **Energia Elétrica** | Contas de energia e gás das áreas comuns | CEMIG, CPFL, Enel, gás (Comgas, CEG) |
| **Água e Esgoto** | Contas de água e esgoto das áreas comuns | COPASA, SABESP, SANEAGO, Caesb |
| **Seguro** | Apólices de seguro do condomínio | Seguro predial, seguro contra incêndio, seguro de elevador |
| **Administração** | Taxa de administração e serviços profissionais | Honorário da administradora, contabilidade, assessoria jurídica |
| **Material de Consumo** | Materiais usados na operação do condomínio | Material de limpeza, papelaria, suprimentos de escritório |
| **Serviços Contratados** | Serviços recorrentes de terceiros | Portaria, vigilância, monitoramento, CFTV, interfone |
| **Tributos** | Impostos e taxas públicas | IPTU, ISS/ISSQN, taxa de bombeiro, taxa de incêndio |
| **Outras Despesas** | Despesas que não se enquadram nas categorias acima | Categoria de fallback — deve ser revisada manualmente |

### 2.2 Categorias de receita

| Categoria | Critérios | Exemplos |
|---|---|---|
| **Condomínio** | Taxa condominial ordinária mensal | Cota condominial das unidades |
| **Cota Extra** | Rateio extraordinário para obras ou despesas imprevistas | Rateio de reforma de fachada |
| **Fundo de Reserva** | Contribuição para o fundo de reserva | Valor da cota destinado ao FDR |
| **Multas e Juros** | Multa condominial e juros de mora por atraso | Multa por inadimplência, juros de mora |
| **Taxa de Mudança** | Taxa cobrada por mudanças de unidades | Taxa de uso do elevador para mudança |
| **Outras Receitas** | Receitas que não se enquadram acima | Aluguel de salão de festas, outras taxas |

### 2.3 Prioridade de classificação

A classificação ocorre em três camadas, nesta ordem:

```
1. Regras determinísticas (categorias.yml)
   └── Se bater: usa categoria e tipo da regra. Para aqui.

2. LLM — campo "categoria_sugerida" e campo "tipo"
   └── Se regra não bateu: usa o que o LLM retornou.

3. Fallback padrão
   └── tipo == "receita" → "Outras Receitas"
   └── tipo == "despesa" → "Outras Despesas"
```

**Regra de desempate:** regras determinísticas sempre sobrescrevem o LLM. Se o LLM diz "Outras Despesas" mas a regra diz "Energia Elétrica", prevalece "Energia Elétrica".

---

## 3. Conciliação bancária

### 3.1 O que é conciliação

Conciliação é o processo de verificar que cada débito no extrato bancário corresponde a uma despesa registrada no balancete, e vice-versa. Discrepâncias indicam:

- Pagamento efetuado mas comprovante não foi enviado ao sistema
- Comprovante registrado mas pagamento ainda não saiu da conta
- Valores ou datas divergentes entre o comprovante e o extrato

### 3.2 O que é conciliado

Apenas **débitos** do extrato são conciliados com **despesas** do balancete. Créditos do extrato (entradas na conta) não participam da conciliação automática — exigiriam mapeamento com receitas, que tem complexidade maior e é feito manualmente.

### 3.3 Critérios de match

Um débito do extrato e uma despesa do balancete são considerados o mesmo evento quando:

| Critério | Tolerância | Motivo |
|---|---|---|
| Valor | ≤ R$ 0,05 | Arredondamentos em boletos e IOF |
| Data | ≤ 3 dias | Compensação bancária pode levar até D+3 |

**Algoritmo best-match:** quando há mais de um candidato possível, o sistema escolhe o par com **menor diferença de data**, desempatando pela **menor diferença de valor**. Isso evita que um match de data exata "roube" outro par melhor.

### 3.4 Resultado da conciliação

| Status | Significado | Ação recomendada |
|---|---|---|
| 🟢 Conciliado | Débito e despesa se encontraram | Nenhuma |
| 🔴 Só no extrato | Débito sem despesa correspondente | Verificar se falta o comprovante |
| 🔵 Só no balancete | Despesa sem débito correspondente | Verificar se o pagamento foi efetuado |

---

## 4. Transações suspeitas

### 4.1 Critérios de suspeição

Uma transação é marcada como suspeita quando qualquer um dos seguintes critérios for verdadeiro:

| Critério | Motivo |
|---|---|
| `valor == 0.0` | LLM não conseguiu extrair o valor (documento ilegível ou mal formatado) |
| `data` ausente | Sem data, não é possível posicionar no período de competência |
| `descricao` ausente | Sem descrição, não é possível auditar a despesa |
| CNPJ presente mas inválido | CNPJ com dígitos verificadores incorretos indica dado corrompido ou inventado |

### 4.2 Como suspeitas são tratadas

**Suspeitas entram nos totais do balancete.** A aba "⚠️ Revisar" é informativa — não exclui as transações do saldo final. O síndico deve revisá-las e corrigir o que for necessário na tela de revisão antes de gerar o XLSX.

**Justificativa:** excluir suspeitas dos totais causaria saldo incorreto sem aviso claro ao usuário. É melhor incluir com alerta do que silenciosamente omitir.

### 4.3 Fluxo de correção

1. Transação extraída com valor 0 → marcada como suspeita → aparece com ⚠️ na tela de revisão
2. Usuário corrige o valor para R$ 500,00 na tela de revisão
3. Ao confirmar, o sistema recalcula `suspeito` baseado nos dados corrigidos (não no emoji)
4. A transação entra nos totais com o valor correto

---

## 5. Formato dos dados

### 5.1 Competência

**Formato:** `AAAA-MM` (ex: `2026-05`)

**Regras:**
- Mês deve ser entre `01` e `12`
- Não aceita `MM/AAAA`, `maio`, `05-2026` nem outros formatos
- Usado como título das abas, nome do arquivo e referência para alertas de data fora do período

### 5.2 Valores monetários

**Formato de entrada (documentos):** o sistema aceita todos os formatos comuns:

| Formato | Exemplo | Origem |
|---|---|---|
| JSON padrão | `1234.56` | LLM bem-comportado |
| BR sem milhar | `1234,56` | Documentos brasileiros simples |
| BR com milhar | `1.234,56` | Documentos brasileiros formais |
| US com milhar | `1,234.56` | Sistemas contábeis importados |
| Com prefixo | `R$ 1.234,56` | Notas fiscais e boletos |

**Regra de desambiguação:** se o valor tem ponto E vírgula, a posição relativa decide — vírgula depois do ponto é BR (1.234,56); ponto depois da vírgula é US (1,234.56). Se só tem vírgula, é BR. Se só tem ponto com exatamente 3 dígitos depois, é separador de milhar.

**Formato de saída (XLSX):** sempre `R$ #,##0.00` (formato nativo do Excel BR).

**Regra de sinal:** valores são sempre armazenados como positivos. O tipo (`despesa` ou `receita`) determina o sinal no cálculo do saldo.

### 5.3 Datas

**Formato de armazenamento:** `AAAA-MM-DD` (ISO 8601).

**Fallback:** se o LLM não conseguir extrair a data, o sistema usa a data atual (`date.today()`). A transação é marcada como suspeita e o síndico deve corrigir.

### 5.4 CNPJ

**Armazenamento:** 14 dígitos sem formatação (ex: `12345678000191`).

**Validação:** dígitos verificadores calculados pelo algoritmo oficial. CNPJ com dígitos inválidos é aceito mas marca a transação como suspeita.

**Não obrigatório:** fornecedores pessoas físicas ou sem CNPJ identificável deixam o campo vazio — não é motivo de suspeição por si só.

---

## 6. Saldo do balancete

### 6.1 Fórmula

```
Saldo Final = Saldo Inicial + Total Receitas - Total Despesas
```

### 6.2 Validação de consistência (planejada)

O sistema deve alertar quando:

```
|saldo_inicial + total_receitas - total_despesas - saldo_final_extrato| > R$ 0,10
```

Essa validação depende do saldo final do extrato bancário, que hoje é extraído mas não cruzado automaticamente com o saldo calculado. É um próximo passo planejado.

---

## 7. Deduplicação de documentos

Se o mesmo arquivo for enviado duas vezes (ou dois comprovantes do mesmo pagamento), o sistema remove duplicatas antes de gerar o balancete.

**Chave de deduplicação:** `(data, valor arredondado em 2 casas, fornecedor em maiúsculas, tipo)`

**Limitação conhecida:** dois pagamentos legítimos com mesma data, valor, fornecedor e tipo (ex: dois técnicos diferentes da mesma empresa no mesmo dia com o mesmo valor) seriam erroneamente deduplicados. Nesse caso, adicionar a `descricao` à chave resolve — mas pode gerar duplicatas reais quando a descrição varia levemente entre documentos do mesmo evento.

---

## 8. Template XLSX personalizado

Administradoras que já possuem um modelo de balancete `.xlsx` podem enviá-lo ao sistema. O sistema substitui os seguintes placeholders nas células e adiciona as abas complementares ao final:

| Placeholder | Substituído por |
|---|---|
| `{{competencia}}` | ex: `2026-05` |
| `{{saldo_inicial}}` | valor numérico com 2 casas decimais |
| `{{total_receitas}}` | soma de todas as receitas |
| `{{total_despesas}}` | soma de todas as despesas |
| `{{saldo_final}}` | saldo_inicial + receitas - despesas |

As abas **Extrato (Referência)**, **Conciliação** e **⚠️ Revisar** são adicionadas ao final do template, preservando toda a formatação original das abas existentes.

---

## 9. Limites e comportamentos de borda

| Situação | Comportamento |
|---|---|
| Documento sem nenhum dado extraível | LLM retorna `tipo_documento: "outro"` — ignorado, sem transação gerada |
| PDF com 0 páginas | `extrair_conteudo_pdf()` retorna texto vazio → processado como escaneado → nenhuma imagem gerada → sem transação |
| Valor negativo retornado pelo LLM | `abs()` aplicado — sempre positivo, tipo define a direção |
| Data fora da competência | Transação é incluída normalmente; alerta visual na tela de revisão |
| Extrato sem movimentações | Aba "Extrato (Referência)" não é gerada |
| Nenhuma despesa | Aba "Conciliação" não é gerada mesmo com extrato |
| Todos os suspeitos corrigidos na revisão | Aba "⚠️ Revisar" não é gerada no XLSX |
