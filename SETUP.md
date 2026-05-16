# SETUP.md — Guia de Instalação

Guia completo para rodar o projeto do zero. Escolha seu sistema operacional:

- [Windows](#windows)
- [Mac (macOS)](#mac-macos)
- [Linux](#linux)
- [Verificação final](#verificação-final)
- [Fluxo diário](#fluxo-diário)
- [Problemas comuns](#problemas-comuns)

---

## Windows

### 1. Python

Baixe o Python 3.11+ em **python.org/downloads**.

> ⚠️ Durante a instalação, marque **"Add Python to PATH"** antes de clicar em Install Now.

Verifique após instalar (abra um **novo** terminal):

```
python --version
```

---

### 2. Ollama

Baixe o instalador em **ollama.com/download** e execute normalmente.

O Ollama instala em `%LOCALAPPDATA%\Programs\Ollama\` e adiciona ao PATH automaticamente. Se o comando `ollama` não for encontrado após instalar:

**Passo 1 — Feche e reabra o terminal completamente** (feche o Windows Terminal inteiro, não só a aba).

**Passo 2 — Se ainda não funcionar, reinicie o computador.**

**Passo 3 — Se persistir, adicione ao PATH manualmente:**

1. `Win + R` → `sysdm.cpl` → Enter
2. **Avançado** → **Variáveis de Ambiente**
3. Em **Variáveis do usuário**, clique em `Path` → **Editar** → **Novo**
4. Cole: `%LOCALAPPDATA%\Programs\Ollama`
5. OK em tudo, reabra o terminal

**Passo 4 — Windows Defender bloqueou o binário?**

Verifique em: **Windows Security → Proteção contra vírus e ameaças → Histórico de proteção**

Se o Ollama estiver listado, clique em **Permitir**. Para evitar bloqueios futuros (PowerShell como administrador):

```powershell
Add-MpPreference -ExclusionPath "$env:LOCALAPPDATA\Programs\Ollama"
Add-MpPreference -ExclusionPath "$env:USERPROFILE\.ollama"
```

Confirme que o servidor está rodando abrindo `http://localhost:11434` no browser. Deve aparecer `Ollama is running`.

---

### 3. Poppler (para PDFs escaneados)

1. Baixe o ZIP mais recente em: **github.com/oschwartz10612/poppler-windows/releases**
2. Extraia para `C:\poppler`
3. Adicione ao PATH do **sistema** (não do usuário):
   - `Win + R` → `sysdm.cpl` → Avançado → Variáveis de Ambiente
   - Em **Variáveis do sistema**, `Path` → Editar → Novo
   - Cole: `C:\poppler\Library\bin`
   - OK em tudo, reabra o terminal
4. Teste: `pdfinfo --version`

---

### 4. Clone e ambiente virtual

Abra o PowerShell:

```powershell
# Clone o repositório
git clone https://github.com/seu-usuario/balancete-condominial.git
cd balancete-condominial

# Crie e ative o ambiente virtual
python -m venv venv
venv\Scripts\activate
```

> Se receber erro de `ExecutionPolicy`:
> ```powershell
> Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
> ```

O prefixo `(venv)` deve aparecer no terminal. **Sempre ative o venv antes de trabalhar.**

---

### 5. Dependências Python

```powershell
pip install -r requirements.txt
```

---

### 6. Modelos de IA

Feito **uma única vez**. Os modelos ficam em `%USERPROFILE%\.ollama\models`.

| Modelo | Uso | Tamanho |
|---|---|---|
| `gemma4:e4b` | Extração de PDFs com texto | ~8 GB |
| `qwen3-vl:8b` | OCR de PDFs escaneados e imagens | ~5 GB |

```powershell
ollama pull gemma4:e4b
ollama pull qwen3-vl:8b
```

Confirme: `ollama list`

---

### 7. Rodar o app

```powershell
streamlit run ui/app.py
```

O browser abre em `http://localhost:8501`.

---

## Mac (macOS)

### 1. Python

```bash
# Via Homebrew (recomendado)
brew install python@3.11

# Ou baixe em python.org/downloads
```

Verifique: `python3 --version`

---

### 2. Ollama

```bash
# Via Homebrew
brew install ollama

# Ou baixe em ollama.com/download
```

Inicie o servidor: `ollama serve` (ou abra o app Ollama da bandeja)

Confirme em `http://localhost:11434`.

---

### 3. Poppler

```bash
brew install poppler
```

Confirme: `pdfinfo --version`

---

### 4. Clone e ambiente virtual

```bash
git clone https://github.com/seu-usuario/balancete-condominial.git
cd balancete-condominial

python3 -m venv venv
source venv/bin/activate
```

---

### 5. Dependências e modelos

```bash
pip install -r requirements.txt

ollama pull gemma4:e4b
ollama pull qwen3-vl:8b
```

---

### 6. Rodar o app

```bash
streamlit run ui/app.py
```

---

## Linux

### 1. Python e dependências do sistema

```bash
# Ubuntu/Debian
sudo apt update
sudo apt install python3.11 python3.11-venv python3-pip poppler-utils git -y

# Fedora/RHEL
sudo dnf install python3.11 poppler-utils git -y
```

---

### 2. Ollama

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

Inicie o servidor: `ollama serve` (ou configure como serviço systemd)

---

### 3. Clone e ambiente virtual

```bash
git clone https://github.com/seu-usuario/balancete-condominial.git
cd balancete-condominial

python3 -m venv venv
source venv/bin/activate
```

---

### 4. Dependências e modelos

```bash
pip install -r requirements.txt

ollama pull gemma4:e4b
ollama pull qwen3-vl:8b
```

---

### 5. Rodar o app

```bash
streamlit run ui/app.py
```

---

## Verificação final

Antes de usar pela primeira vez, rode o script de verificação:

```bash
python scripts/check_env.py
```

Ele verifica:
- Python 3.11+
- Ollama rodando em localhost:11434
- Modelos `gemma4:e4b` e `qwen3-vl:8b` disponíveis
- Poppler instalado (`pdfinfo`)
- Todas as dependências Python instaladas

Saída esperada:

```
✅ Python 3.11.x
✅ Ollama rodando em localhost:11434
✅ Modelo gemma4:e4b disponível
✅ Modelo qwen3-vl:8b disponível
✅ Poppler (pdfinfo) disponível
✅ Todas as dependências Python instaladas

Ambiente pronto. Execute: streamlit run ui/app.py
```

---

## Fluxo diário

### Windows
```powershell
cd C:\caminho\balancete-condominial
venv\Scripts\activate
streamlit run ui/app.py
```
> O Ollama inicia automaticamente com o Windows — confirme o ícone na bandeja do sistema.

### Mac / Linux
```bash
cd ~/balancete-condominial
source venv/bin/activate
streamlit run ui/app.py
```
> Certifique-se de que `ollama serve` está rodando em outro terminal, ou que o app Ollama está aberto.

---

## Problemas comuns

| Problema | Causa provável | Solução |
|---|---|---|
| `'ollama' is not recognized` | Terminal não recarregou o PATH | Feche e reabra o terminal; se persistir, reinicie o PC |
| `'ollama' is not recognized` (após reiniciar) | Instalação falhou ou Defender bloqueou | Reinstale como administrador; verifique o Histórico do Defender |
| `'streamlit' is not recognized` | venv não está ativado | Execute o comando de ativação do venv antes |
| `ExecutionPolicy` bloqueando o venv | Política de scripts do PowerShell | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| `Is poppler installed and in PATH?` | Poppler não está no PATH | Confirme o caminho correto; reabra o terminal |
| `connection refused` na porta 11434 | Ollama não está rodando | Procure o ícone na bandeja ou execute `ollama serve` |
| GPU não utilizada (100% CPU) | Driver NVIDIA desatualizado ou VRAM insuficiente | Atualize drivers; Ollama detecta CUDA automaticamente |
| Acentos quebrados no terminal (Windows) | Codepage padrão do Windows | Execute `chcp 65001` antes de rodar o Streamlit |
| `ModuleNotFoundError` | Dependência não instalada | `pip install -r requirements.txt` com o venv ativado |
| App abre mas não processa nenhum arquivo | Modelo não baixado | `ollama list` para confirmar; `ollama pull <modelo>` se ausente |
