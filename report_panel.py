"""
Streamlit panel: report generation UI.

Entry point: ``render_report_panel()`` — called from the main app
inside a tab, following the same pattern as ``compstat.py``.
"""
from __future__ import annotations

from datetime import datetime

import streamlit as st


def _load_areas() -> list[dict]:
    """Lazy-import backend areas list."""
    from report_adapter import listar_areas
    return listar_areas()


def render_report_panel() -> None:
    st.header("Gerar Relatório CompStat")
    st.caption(
        "Selecione a área de interesse e o período de análise. "
        "O relatório PDF será gerado com mapas, indicadores e plano de ação."
    )

    # ── Area selection ───────────────────────────────────────────────────
    try:
        areas = _load_areas()
    except Exception as exc:
        st.error(f"Erro ao carregar áreas do shapefile: {exc}")
        return

    area_options = {f"{a['fid']} — {a['nome']}": a["fid"] for a in areas}
    area_label = st.selectbox(
        "Área FM",
        list(area_options.keys()),
        help="Selecione a área da Força Municipal para o relatório.",
    )
    fid = area_options[area_label]

    # ── Period selection ─────────────────────────────────────────────────
    col1, col2, col3 = st.columns(3)
    with col1:
        ano_inicio = st.number_input("Ano início", min_value=2018, max_value=2030, value=2023)
    with col2:
        ano_fim = st.number_input("Ano fim", min_value=2018, max_value=2030, value=2024)
    with col3:
        mes_ref = st.text_input("Mês de referência", value="Maio 2026")

    if ano_fim < ano_inicio:
        st.warning("Ano fim deve ser maior ou igual ao ano início.")
        return

    # ── Options ──────────────────────────────────────────────────────────
    col_opt1, col_opt2 = st.columns(2)
    with col_opt1:
        gerar_mapas = st.checkbox("Gerar mapas e gráficos", value=True)
    with col_opt2:
        preview_html = st.checkbox("Pré-visualizar HTML antes do PDF", value=False)

    st.divider()

    # ── Generate button ──────────────────────────────────────────────────
    if not st.button("Gerar Relatório", type="primary", use_container_width=True):
        return

    from report_adapter import (
        gerar_contexto_relatorio,
        generate_pdf_bytes,
        generate_html_string,
        check_playwright,
    )

    progress = st.progress(0, text="Carregando dados e filtrando por área…")

    try:
        progress.progress(10, text="Calculando contexto do relatório…")
        ctx = gerar_contexto_relatorio(
            shapefile_fid=fid,
            ano_inicio=int(ano_inicio),
            ano_fim=int(ano_fim),
            mes_referencia=mes_ref,
            gerar_mapas=gerar_mapas,
        )
        progress.progress(60, text="Contexto pronto. Gerando saídas…")
    except Exception as exc:
        progress.empty()
        st.error(f"Erro ao gerar contexto: {exc}")
        return

    # ── Summary metrics ──────────────────────────────────────────────────
    ind = ctx.get("indicadores", {})
    cam = ctx.get("cameras", {})
    ident = ctx.get("identificacao", {})

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Ocorrências no período", f"{ind.get('total', 0):,}")
    m2.metric("Ranking", f"{ind.get('ranking_pos', '?')}º de {ind.get('ranking_total_areas', '?')}")
    m3.metric("Câmeras", cam.get("total", 0))
    m4.metric("Grupos criminosos", ident.get("grupos_criminosos", "—"))

    # ── HTML preview ─────────────────────────────────────────────────────
    html_str = generate_html_string(ctx)

    if preview_html:
        progress.progress(70, text="Renderizando pré-visualização HTML…")
        with st.expander("Pré-visualização do relatório (HTML)", expanded=True):
            st.components.v1.html(html_str, height=800, scrolling=True)

    # ── PDF generation ───────────────────────────────────────────────────
    playwright_ok = check_playwright()

    if playwright_ok:
        progress.progress(80, text="Gerando PDF via Playwright…")
        try:
            pdf_bytes = generate_pdf_bytes(ctx)
            progress.progress(100, text="Relatório pronto!")
        except Exception as exc:
            progress.empty()
            st.error(f"Erro ao gerar PDF: {exc}")
            pdf_bytes = None
    else:
        progress.progress(100, text="Relatório pronto (PDF indisponível — Playwright não instalado).")
        pdf_bytes = None
        st.warning(
            "Playwright não está instalado. O download em PDF não está disponível.\n\n"
            "Para instalar, execute:\n"
            "```\npip install playwright && playwright install chromium\n```"
        )

    # ── Download buttons ─────────────────────────────────────────────────
    st.divider()
    safe_name = ctx["meta"]["nome_area"].replace("/", "-").replace(" ", "_")[:40]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")

    dl1, dl2 = st.columns(2)
    if pdf_bytes:
        with dl1:
            st.download_button(
                "Baixar PDF",
                data=pdf_bytes,
                file_name=f"relatorio_{safe_name}_{timestamp}.pdf",
                mime="application/pdf",
                use_container_width=True,
            )
    with dl2:
        st.download_button(
            "Baixar HTML",
            data=html_str.encode("utf-8"),
            file_name=f"relatorio_{safe_name}_{timestamp}.html",
            mime="text/html",
            use_container_width=True,
        )
