"""
Seção 1 — Ocorrências Criminais
Calculates all deterministic indicators from filtered crime data.
"""
from __future__ import annotations

import pandas as pd
from typing import Optional

from config import CRIME_TYPES, DIAS_SEMANA, get_aisp_info


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _filter_period(df: pd.DataFrame, ano_inicio: int, ano_fim: int) -> pd.DataFrame:
    return df[(df["ano"] >= ano_inicio) & (df["ano"] <= ano_fim)].copy()


def _filter_period_prev(df: pd.DataFrame, ano_inicio: int, ano_fim: int) -> pd.DataFrame:
    """Returns the equivalent prior window (same duration, ending just before ano_inicio)."""
    span = ano_fim - ano_inicio
    return df[
        (df["ano"] >= ano_inicio - span - 1) &
        (df["ano"] <= ano_inicio - 1)
    ].copy()


def _pct_change(current: int, previous: int) -> Optional[float]:
    if previous == 0:
        return None
    return round((current - previous) / previous * 100, 1)


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def calcular_identificacao(
    df_area: pd.DataFrame,
    nome_area: str,
    dominios: list[dict],
    df_fatores: pd.DataFrame | None = None,
) -> dict:
    """
    Returns area metadata block.

    df_area:    all crime records inside the polygon (no period filter)
    nome_area:  display name from cameras_areas_fm
    dominios:   output of spatial.filter_dominio()
    df_fatores: fatores_urbanos filtered by polygon — used for bairro lookup
    """
    aisp_val = int(df_area["aisp"].mode().iloc[0]) if not df_area.empty else None
    aisp_display = str(aisp_val) if aisp_val else "—"
    aisp_info = get_aisp_info(aisp_val) if aisp_val else {"dp": "—", "bpm": "—"}

    # Bairro: prefer fatores_urbanos (has clean bairro_nome), fallback to crime data
    if df_fatores is not None and not df_fatores.empty and "bairro_nome" in df_fatores.columns:
        bairros = (
            df_fatores["bairro_nome"].dropna()
            .str.strip()
            .value_counts()
            .head(3)
            .index.tolist()
        )
    elif "bairro_nome" in df_area.columns:
        bairros = df_area["bairro_nome"].dropna().value_counts().head(3).index.tolist()
    else:
        bairros = []

    # Criminal groups: direct intersection or nearby
    grupos_diretos   = sorted({d["orcrim"] for d in dominios if d.get("tipo") == "intersecta"})
    grupos_proximos  = sorted({d["orcrim"] for d in dominios if d.get("tipo") == "proximidade"})
    grupos = grupos_diretos or grupos_proximos  # prefer direct, fallback to proximity

    # Top 5 critical street segments
    trechos = (
        df_area["locf"]
        .dropna()
        .str.strip()
        .str.title()
        .value_counts()
        .head(5)
        .reset_index()
        .rename(columns={"locf": "logradouro", "count": "ocorrencias"})
        .to_dict("records")
    )

    # Build display string: direct groups or "Comunidades próximas sob domínio de X"
    if grupos_diretos:
        grupos_str = " / ".join(grupos_diretos)
    elif grupos_proximos:
        comunidades = [d["nome"] for d in dominios if d.get("tipo") == "proximidade"]
        grupos_str = f"Comunidades próximas sob domínio do {' / '.join(grupos_proximos)}"
    else:
        grupos_str = "Não identificado"

    return {
        "nome_area":          nome_area,
        "n_trechos_criticos": len(trechos),
        "trechos_criticos":   trechos,
        "aisp":               aisp_display,
        "dp":                 aisp_info["dp"],
        "bpm":                aisp_info["bpm"],
        "bairros":            " / ".join(bairros) if bairros else "—",
        "grupos_criminosos":  grupos_str,
        "dominios_lista":     dominios,
    }


def calcular_indicadores(
    df_area: pd.DataFrame,
    ano_inicio: int,
    ano_fim: int,
) -> dict:
    """
    Returns period indicators: totals, variation, ranking placeholder.
    Ranking must be injected by the orchestrator after computing all areas.
    """
    df_periodo   = _filter_period(df_area, ano_inicio, ano_fim)
    df_anterior  = _filter_period_prev(df_area, ano_inicio, ano_fim)

    total       = len(df_periodo)
    total_prev  = len(df_anterior)
    roubos      = len(df_periodo[df_periodo["desc_delito"].str.startswith("Roubo", na=False)])
    furtos      = len(df_periodo[df_periodo["desc_delito"].str.startswith("Furto", na=False)])

    # Monthly series for chart
    serie_mensal = (
        df_periodo.groupby(["ano", "mes"])
        .size()
        .reset_index(name="total")
        .sort_values(["ano", "mes"])
        .to_dict("records")
    )

    return {
        "periodo":         f"{ano_inicio}–{ano_fim}",
        "total":           total,
        "roubos":          roubos,
        "furtos":          furtos,
        "variacao_pct":    _pct_change(total, total_prev),
        "total_anterior":  total_prev,
        "serie_mensal":    serie_mensal,
        # ranking is filled later by the orchestrator
        "ranking_pos":     None,
        "ranking_pct":     None,
    }


def calcular_distribuicao_tipos(
    df_area: pd.DataFrame,
    ano_inicio: int,
    ano_fim: int,
) -> list[dict]:
    """
    Returns top crime types ranked by count within the period,
    with count, last occurrence date, and period-over-period variation.
    """
    df_p = _filter_period(df_area, ano_inicio, ano_fim)
    df_a = _filter_period_prev(df_area, ano_inicio, ano_fim)

    results = []
    for delito in CRIME_TYPES:
        cur  = df_p[df_p["desc_delito"] == delito]
        prev = df_a[df_a["desc_delito"] == delito]

        last_date = None
        if "data" in cur.columns and not cur["data"].dropna().empty:
            last_date = cur["data"].dropna().max()

        results.append({
            "tipo":          delito,
            "quantidade":    len(cur),
            "ultima_data":   str(last_date) if last_date else "—",
            "variacao_pct":  _pct_change(len(cur), len(prev)),
        })

    results.sort(key=lambda x: -x["quantidade"])
    for i, r in enumerate(results):
        r["ranking"] = i + 1
    return results


def calcular_heatmap_temporal(
    df_area: pd.DataFrame,
    ano_inicio: int,
    ano_fim: int,
) -> dict:
    """
    Returns a dict suitable for rendering the hour×weekday heatmap,
    plus a text summary of the dominant period.
    """
    df_p = _filter_period(df_area, ano_inicio, ano_fim)
    df_p = df_p.dropna(subset=["hora", "dia_semana"])

    if df_p.empty:
        return {"matrix": [], "hora_pico": None, "dia_pico": None, "resumo_texto": "Sem dados"}

    df_p["hora"]       = df_p["hora"].astype(int)
    df_p["dia_semana"] = df_p["dia_semana"].astype(int)

    pivot = (
        df_p.groupby(["hora", "dia_semana"])
        .size()
        .reset_index(name="count")
    )

    # Build matrix [hora][dia] for template
    hours    = list(range(0, 24))
    days     = sorted(df_p["dia_semana"].unique().tolist())
    day_labels = [DIAS_SEMANA.get(str(d), str(d)) for d in days]

    matrix = {}
    for _, row in pivot.iterrows():
        h = int(row["hora"])
        d = int(row["dia_semana"])
        matrix[(h, d)] = int(row["count"])

    max_val = max(matrix.values()) if matrix else 1
    grid = []
    for h in hours:
        row_data = []
        for d in days:
            val = matrix.get((h, d), 0)
            row_data.append({"hora": h, "dia": d, "count": val, "intensity": val / max_val})
        grid.append(row_data)

    # Dominant period
    hora_pico = int(pivot.loc[pivot["count"].idxmax(), "hora"])
    dia_pico  = int(pivot.loc[pivot["count"].idxmax(), "dia_semana"])

    # Hour range with most activity (where sum > 50% of max hour)
    hora_totals = df_p.groupby("hora").size()
    threshold   = hora_totals.max() * 0.6
    horas_criticas = sorted(hora_totals[hora_totals >= threshold].index.tolist())
    if horas_criticas:
        h_inicio = horas_criticas[0]
        h_fim    = horas_criticas[-1]
    else:
        h_inicio = h_fim = hora_pico

    dia_nome = DIAS_SEMANA.get(str(dia_pico), str(dia_pico))

    resumo = (
        f"Todos os dias entre {h_inicio:02d}h e {h_fim:02d}h, "
        f"com pico às {hora_pico:02d}h. "
        f"Maior concentração: {dia_nome}."
    )

    return {
        "matrix":      grid,
        "days":        days,
        "day_labels":  day_labels,
        "hours":       hours,
        "hora_pico":   hora_pico,
        "dia_pico":    dia_pico,
        "h_inicio":    h_inicio,
        "h_fim":       h_fim,
        "resumo_texto": resumo,
        "max_val":     max_val,
    }
