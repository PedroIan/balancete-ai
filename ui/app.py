"""
ui/app.py
Interface Streamlit — orquestrador das três telas do balancete condominial.
Não contém lógica de negócio: toda computação é delegada a core/.
"""

from __future__ import annotations

import math
import os
import re
import shutil
import tempfile
import zipfile
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st

from core.classifier import TEXTO_MODEL, VISAO_MODEL, extrair_de_imagem, extrair_de_texto
from core.conciliacao import gerar_xlsx, preencher_template
from core.extractor import (
    ConteudoPDF,
    _TESSERACT_CHARS_MIN,
    _TESSERACT_CONFIANCA_MIN,
    bytes_para_b64,
    carregar_imagem_b64,
    extrair_conteudo_pdf,
    ocr_com_tesseract,
    redimensionar_imagem,
)

_CACHE_DIR = Path.home() / ".balancete_cache" / "imagens"
_CACHE_DIR.mkdir(parents=True, exist_ok=True)


def main() -> None:
    st.set_page_config(page_title="Balancete Condominial", page_icon="🏢", layout="wide")
    st.title("🏢 Balancete Condominial")
    st.caption("Processamento 100% local — nenhum dado sai da sua máquina.")

    if "tela" not in st.session_state:
        st.session_state.tela = "configuracao"
    if "dados_extraidos" not in st.session_state:
        st.session_state.dados_extraidos = {"transacoes": [], "extrato_movs": [], "caminhos_imagens": []}
    if "resultado" not in st.session_state:
        st.session_state.resultado = None

    if st.session_state.tela == "configuracao":
        _tela_configuracao()
    elif st.session_state.tela == "revisao":
        _tela_revisao()
    elif st.session_state.tela == "download":
        _tela_download()


# ── Tela 1: Configuração ─────────────────────────────────────────────────────

def _tela_configuracao() -> None:
    st.header("Configuração")

    col1, col2 = st.columns(2)
    with col1:
        competencia = st.text_input("Competência (AAAA-MM)", placeholder="Ex: 2026-05")
    with col2:
        saldo_inicial = st.number_input("Saldo inicial (R$)", min_value=0.0, step=0.01, format="%.2f")

    arquivos = st.file_uploader(
        "Documentos financeiros",
        type=["pdf", "png", "jpg", "jpeg"],
        accept_multiple_files=True,
        help="Extratos bancários, comprovantes, recibos e notas fiscais.",
    )
    template = st.file_uploader("Template XLSX personalizado (opcional)", type=["xlsx"])

    if st.button("Processar documentos", type="primary", disabled=not arquivos):
        erro = _validar_competencia(competencia)
        if erro:
            st.error(erro)
            return

        shutil.rmtree(_CACHE_DIR, ignore_errors=True)
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)

        st.session_state.dados_extraidos = {
            "transacoes": [], "extrato_movs": [], "caminhos_imagens": [], "status_docs": [],
        }
        st.session_state.competencia = competencia
        st.session_state.saldo_inicial = saldo_inicial
        st.session_state.template_bytes = template.read() if template else None

        total = len(arquivos)
        progresso = st.progress(0.0, text=f"0 de {total} arquivo(s) processado(s)")
        status_docs: List[Dict] = []

        for idx, arquivo in enumerate(arquivos):
            entrada = {"Arquivo": arquivo.name, "Resultado": "❌ Falha", "Transações": 0, "Mov. Extrato": 0, "Detalhe": ""}
            with st.status(f"📄 [{idx + 1}/{total}] {arquivo.name}", expanded=True) as status:
                try:
                    n_txs, n_movs, avisos = _processar_arquivo(arquivo, status)
                    entrada["Transações"] = n_txs
                    entrada["Mov. Extrato"] = n_movs
                    if avisos:
                        entrada["Resultado"] = "⚠️ Atenção"
                        entrada["Detalhe"] = "; ".join(avisos)
                        icone = "⚠️"
                    elif n_txs == 0 and n_movs == 0:
                        entrada["Resultado"] = "⚠️ Atenção"
                        entrada["Detalhe"] = "nenhum dado extraído"
                        icone = "⚠️"
                    else:
                        entrada["Resultado"] = "✅ OK"
                        icone = "✅"
                    status.update(label=f"{icone} [{idx + 1}/{total}] {arquivo.name}", state="complete", expanded=False)
                except Exception as e:
                    entrada["Detalhe"] = str(e)
                    status.update(label=f"❌ [{idx + 1}/{total}] {arquivo.name} — erro", state="error", expanded=True)
                    status.write(f"Detalhe: {e}")

            status_docs.append(entrada)
            progresso.progress((idx + 1) / total, text=f"{idx + 1} de {total} arquivo(s) processado(s)")

        st.session_state.dados_extraidos["status_docs"] = status_docs

        with st.status("🔄 Deduplicando transações...", expanded=False) as s_dedup:
            txs = st.session_state.dados_extraidos["transacoes"]
            antes = len(txs)
            txs = _deduplicar_transacoes(txs)
            st.session_state.dados_extraidos["transacoes"] = txs
            removidas = antes - len(txs)
            label_dedup = f"✅ {len(txs)} transação(ões) únicas"
            if removidas:
                label_dedup += f" — {removidas} duplicata(s) removida(s)"
            s_dedup.update(label=label_dedup, state="complete")

        progresso.progress(1.0, text=f"✅ {total} arquivo(s) processado(s)")
        st.session_state.tela = "revisao"
        st.rerun()


# ── Tela 2: Revisão ──────────────────────────────────────────────────────────

def _tela_revisao() -> None:
    st.header("Revisão das transações extraídas")
    dados = st.session_state.dados_extraidos
    transacoes = dados.get("transacoes", [])
    extrato_movs = dados.get("extrato_movs", [])
    competencia = st.session_state.get("competencia", "")

    col_voltar, col_confirmar = st.columns([1, 4])
    with col_voltar:
        if st.button("← Voltar"):
            st.session_state.tela = "configuracao"
            st.rerun()

    status_docs = dados.get("status_docs", [])
    if status_docs:
        n_ok = sum(1 for s in status_docs if s["Resultado"] == "✅ OK")
        n_atencao = len(status_docs) - n_ok
        with st.expander(
            f"📋 Resumo do processamento — {n_ok} OK · {n_atencao} com atenção/falha",
            expanded=(n_atencao > 0),
        ):
            st.dataframe(pd.DataFrame(status_docs), use_container_width=True, hide_index=True)

    if not transacoes and not extrato_movs:
        st.warning("Nenhum dado extraído. Verifique os documentos enviados.")
        return

    pendencias: List[Dict] = []
    gerar_mesmo_assim = False

    tab_tx, tab_ext = st.tabs(["Transações", "Extrato (Referência)"])

    with tab_tx:
        if transacoes:
            df_tx = pd.DataFrame(transacoes)
            if "suspeito" in df_tx.columns:
                df_tx["⚠️"] = df_tx["suspeito"].apply(lambda s: "⚠️" if s else "")
            colunas_editor = [
                "⚠️", "data", "tipo", "valor", "categoria",
                "fonte_pagadora", "prestador_destino", "cnpj",
                "numero_documento", "descricao", "fonte",
            ]
            colunas_editor = [c for c in colunas_editor if c in df_tx.columns]

            editado = st.data_editor(
                df_tx[colunas_editor],
                use_container_width=True,
                num_rows="dynamic",
                column_config={
                    "valor": st.column_config.NumberColumn("Valor (R$)", format="%.2f"),
                    "data": st.column_config.TextColumn("Data (AAAA-MM-DD)"),
                    "tipo": st.column_config.SelectboxColumn("Tipo", options=["receita", "despesa"]),
                    "fonte_pagadora": st.column_config.TextColumn("Fonte Pagadora"),
                    "prestador_destino": st.column_config.TextColumn("Prestador/Destino"),
                    "numero_documento": st.column_config.TextColumn("Nº Doc."),
                    "⚠️": st.column_config.TextColumn("⚠️", disabled=True, width="small"),
                },
                key="editor_transacoes",
            )
            st.session_state.dados_extraidos["transacoes_editadas"] = editado.to_dict("records")
            pendencias = _calcular_pendencias(editado.to_dict("records"))
        else:
            st.info("Nenhuma transação extraída.")
            st.session_state.dados_extraidos["transacoes_editadas"] = []

    with tab_ext:
        if extrato_movs:
            df_ext = pd.DataFrame(extrato_movs)
            st.dataframe(df_ext, use_container_width=True)
        else:
            st.info("Nenhum extrato bancário enviado.")

    if transacoes and competencia:
        ano_mes = competencia[:7]
        fora = [t for t in transacoes if t.get("data") and not t["data"].startswith(ano_mes)]
        if fora:
            st.warning(f"⚠️ {len(fora)} transação(ões) com data fora da competência {competencia}.")

    if pendencias:
        st.error(
            f"**{len(pendencias)} transação(ões) com campos obrigatórios em branco.** "
            "Corrija na tabela acima ou marque que deseja gerar mesmo assim."
        )
        st.dataframe(pd.DataFrame(pendencias), use_container_width=True, hide_index=True)
        gerar_mesmo_assim = st.checkbox(
            "⚠️ Entendo que há transações incompletas e desejo gerar o balancete mesmo assim"
        )

    with col_confirmar:
        pode_confirmar = not pendencias or gerar_mesmo_assim
        if st.button("✅ Confirmar e gerar XLSX", type="primary", disabled=not pode_confirmar):
            _gerar_resultado()
            st.session_state.tela = "download"
            st.rerun()


# ── Tela 3: Download ─────────────────────────────────────────────────────────

def _tela_download() -> None:
    st.header("Download do balancete")
    resultado = st.session_state.get("resultado")
    competencia = st.session_state.get("competencia", "balancete")

    col_voltar, _ = st.columns([1, 4])
    with col_voltar:
        if st.button("← Nova análise"):
            st.session_state.tela = "configuracao"
            st.session_state.resultado = None
            st.session_state.dados_extraidos = {"transacoes": [], "extrato_movs": [], "caminhos_imagens": []}
            st.rerun()

    if not resultado:
        st.error("Nenhum resultado disponível. Volte e processe os documentos.")
        return

    st.success("Balancete gerado com sucesso!")
    st.download_button(
        label="⬇️ Baixar Balancete XLSX",
        data=resultado["xlsx"],
        file_name=f"balancete_{competencia}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    caminhos_imagens = st.session_state.dados_extraidos.get("caminhos_imagens", [])
    if caminhos_imagens:
        zip_bytes = _criar_zip_imagens(caminhos_imagens)
        if zip_bytes:
            st.download_button(
                label="⬇️ Baixar imagens das páginas (ZIP)",
                data=zip_bytes,
                file_name=f"imagens_{competencia}.zip",
                mime="application/zip",
            )


# ── Funções auxiliares ───────────────────────────────────────────────────────

def _processar_arquivo(arquivo, status) -> Tuple[int, int, List[str]]:
    status.write("🔍 Etapa 1/3 — Detectando tipo de documento...")

    with tempfile.NamedTemporaryFile(suffix=Path(arquivo.name).suffix, delete=False) as tmp:
        tmp.write(arquivo.read())
        tmp_path = Path(tmp.name)

    n_txs = 0
    n_movs = 0
    avisos: List[str] = []

    try:
        conteudo: ConteudoPDF = extrair_conteudo_pdf(tmp_path)

        if conteudo.tem_texto:
            status.write(f"📄 Etapa 2/3 — PDF digital: {len(conteudo.texto):,} caracteres extraídos")
            status.write(f"🤖 Etapa 3/3 — Classificando via LLM ({TEXTO_MODEL})... aguarde")
            txs, movs, aviso = extrair_de_texto(conteudo.texto, arquivo.name)
            if aviso:
                status.write(f"⚠️ Documento descartado: {aviso}")
                avisos.append(aviso)
            status.write(f"✅ {len(txs)} transação(ões) · {len(movs)} movimentação(ões) de extrato")
            st.session_state.dados_extraidos["transacoes"].extend(txs)
            st.session_state.dados_extraidos["extrato_movs"].extend(movs)
            n_txs += len(txs)
            n_movs += len(movs)

        elif conteudo.imagens:
            n_pags = len(conteudo.imagens)
            status.write(f"🖼️ Etapa 2/3 — PDF escaneado: {n_pags} página(s) detectada(s)")
            caminhos = _salvar_imagens_em_disco(conteudo.imagens, arquivo.name)
            st.session_state.dados_extraidos["caminhos_imagens"].extend(caminhos)

            for num_pag, img_bytes in conteudo.imagens:
                fonte = f"{arquivo.name} (pág. {num_pag})"
                status.write(f"  📷 Pág. {num_pag}/{n_pags} — OCR Tesseract...")
                texto_ocr, confianca = ocr_com_tesseract(img_bytes)

                if confianca >= _TESSERACT_CONFIANCA_MIN and len(texto_ocr) >= _TESSERACT_CHARS_MIN:
                    status.write(f"  ✅ Tesseract ({confianca:.0f}%) → 🤖 {TEXTO_MODEL}... aguarde")
                    txs, movs, aviso = extrair_de_texto(texto_ocr, fonte)
                else:
                    motivo = (
                        f"confiança {confianca:.0f}% < {_TESSERACT_CONFIANCA_MIN:.0f}%"
                        if texto_ocr else "Tesseract indisponível"
                    )
                    status.write(f"  🔄 {motivo} → reduzindo para 150 DPI → 🤖 {VISAO_MODEL}... aguarde")
                    img_reduzida = redimensionar_imagem(img_bytes, fator=0.5)
                    img_b64 = bytes_para_b64(img_reduzida)
                    txs, movs, aviso = extrair_de_imagem(img_b64, fonte)

                if aviso:
                    status.write(f"  ⚠️ Pág. {num_pag} descartada: {aviso}")
                    avisos.append(f"pág. {num_pag}: {aviso}")
                status.write(f"  ✅ Pág. {num_pag}: {len(txs)} transação(ões) · {len(movs)} mov.")
                st.session_state.dados_extraidos["transacoes"].extend(txs)
                st.session_state.dados_extraidos["extrato_movs"].extend(movs)
                n_txs += len(txs)
                n_movs += len(movs)

        else:
            status.write("⚠️ Nenhum conteúdo extraível neste documento")
            avisos.append("nenhum conteúdo extraível")
    finally:
        tmp_path.unlink(missing_ok=True)

    return (n_txs, n_movs, avisos)


def _gerar_resultado() -> None:
    dados = st.session_state.dados_extraidos
    txs_editadas = dados.get("transacoes_editadas", dados.get("transacoes", []))
    transacoes = _reconstruir_transacoes(txs_editadas)
    extrato_movs = dados.get("extrato_movs", [])
    competencia = st.session_state.get("competencia", "")
    saldo_inicial = st.session_state.get("saldo_inicial", 0.0)
    template_bytes = st.session_state.get("template_bytes")

    if template_bytes:
        xlsx = preencher_template(template_bytes, transacoes, extrato_movs, competencia, saldo_inicial)
    else:
        xlsx = gerar_xlsx(transacoes, extrato_movs, competencia, saldo_inicial)
    st.session_state.resultado = {"xlsx": xlsx}


def _num_seguro(valor) -> float:
    try:
        f = float(valor)
        return 0.0 if f != f else f  # NaN != NaN
    except (TypeError, ValueError):
        return 0.0


def _texto_seguro(valor) -> str:
    if valor is None or valor != valor:
        return ""
    return str(valor).strip()


def _calcular_pendencias(txs_editadas: List[Dict]) -> List[Dict]:
    pendencias: List[Dict] = []
    for idx, t in enumerate(txs_editadas):
        if _linha_vazia(t):
            continue
        faltando = []
        if not _texto_seguro(t.get("data")):
            faltando.append("data")
        if _num_seguro(t.get("valor")) == 0.0:
            faltando.append("valor")
        if not _texto_seguro(t.get("descricao")):
            faltando.append("descrição")
        if faltando:
            pendencias.append({"Linha": idx + 1, "Arquivo": _texto_seguro(t.get("fonte")), "Campos faltando": ", ".join(faltando)})
    return pendencias


def _linha_vazia(t: Dict) -> bool:
    return (
        _num_seguro(t.get("valor")) == 0.0
        and not _texto_seguro(t.get("descricao"))
        and not _texto_seguro(t.get("prestador_destino"))
    )


def _reconstruir_transacoes(txs_editadas: List[Dict]) -> List[Dict]:
    from core.classifier import _validar_cnpj

    resultado = []
    for t in txs_editadas:
        if _linha_vazia(t):
            continue
        valor = abs(_num_seguro(t.get("valor")))
        descricao = _texto_seguro(t.get("descricao"))
        data_str = _texto_seguro(t.get("data"))
        cnpj_raw = _texto_seguro(t.get("cnpj"))

        if cnpj_raw:
            cnpj_limpo, cnpj_valido = _validar_cnpj(cnpj_raw)
        else:
            cnpj_limpo, cnpj_valido = ("", False)

        suspeito = (
            valor == 0.0
            or not data_str
            or not descricao
            or (bool(cnpj_limpo) and not cnpj_valido)
        )

        resultado.append({
            "data": data_str or date.today().isoformat(),
            "fonte_pagadora": _texto_seguro(t.get("fonte_pagadora")),
            "prestador_destino": _texto_seguro(t.get("prestador_destino")),
            "cnpj": cnpj_limpo,
            "descricao": descricao,
            "numero_documento": _texto_seguro(t.get("numero_documento")),
            "valor": valor,
            "tipo": t.get("tipo", "despesa"),
            "categoria": _texto_seguro(t.get("categoria")) or "Outras Despesas",
            "suspeito": suspeito,
            "fonte": _texto_seguro(t.get("fonte")),
        })
    return resultado


def _salvar_imagens_em_disco(imagens: List[Tuple[int, bytes]], nome_arquivo: str) -> List[Path]:
    caminhos: List[Path] = []
    base = re.sub(r"[^\w\-]", "_", Path(nome_arquivo).stem)
    for num, img_bytes in imagens:
        caminho = _CACHE_DIR / f"{base}_p{num:03d}.png"
        caminho.write_bytes(img_bytes)
        caminhos.append(caminho)
    return caminhos


def _deduplicar_transacoes(transacoes: List[Dict]) -> List[Dict]:
    vistas: set = set()
    unicas: List[Dict] = []
    for t in transacoes:
        num_doc = str(t.get("numero_documento") or "").strip()
        if num_doc:
            chave = ("doc", num_doc, t.get("tipo", ""))
        else:
            chave = (
                t.get("data") or "",
                round(float(t.get("valor") or 0), 2),
                str(t.get("prestador_destino") or "").upper(),
                t.get("tipo", ""),
            )
        if chave not in vistas:
            vistas.add(chave)
            unicas.append(t)
    return unicas


def _validar_competencia(competencia: str) -> Optional[str]:
    if not competencia:
        return "Informe a competência no formato AAAA-MM."
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", competencia):
        return "Competência inválida. Use o formato AAAA-MM (ex: 2026-05)."
    return None


def _criar_zip_imagens(caminhos: List[Path]) -> Optional[bytes]:
    import io as _io
    buf = _io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for caminho in caminhos:
            if Path(caminho).exists():
                zf.write(caminho, arcname=Path(caminho).name)
    conteudo = buf.getvalue()
    return conteudo if conteudo else None


if __name__ == "__main__":
    main()
