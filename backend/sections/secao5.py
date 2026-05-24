"""
Seção 5 — Painel de Coincidências & Resumo Executivo
Deterministic cross-reference between crime hotspots and urban factors.
"""
from __future__ import annotations

import pandas as pd

_PROXIMITY_DEG = 0.0007  # ~70 m at Rio's latitude (~22 S)


def calcular_coincidencias(
    df_oc_periodo: pd.DataFrame,
    df_fatores: pd.DataFrame,
    trechos_criticos: list[dict],
) -> list[dict]:
    """
    For each critical trecho, compute the centroid of its crime cluster and
    search for fatores_urbanos within _PROXIMITY_DEG degrees (~70 m).

    Returns a list of dicts ordered by crime count, each with:
        trecho, ocorrencias, fatores (list of str), coincidencia (bool)
    """
    results = []

    for trecho in trechos_criticos:
        nome = trecho["logradouro"]

        crimes = df_oc_periodo[
            df_oc_periodo["locf"].str.strip().str.title() == nome
        ].dropna(subset=["latitude", "longitude"])

        if crimes.empty:
            results.append({
                "trecho":      nome,
                "ocorrencias": trecho["ocorrencias"],
                "fatores":     [],
                "coincidencia": False,
            })
            continue

        lat_c = crimes["latitude"].mean()
        lon_c = crimes["longitude"].mean()

        fatores_near: list[str] = []
        if not df_fatores.empty and "coordenada_x" in df_fatores.columns:
            # coordenada_x = latitude, coordenada_y = longitude (non-standard naming)
            mask = (
                (abs(df_fatores["coordenada_x"] - lat_c) < _PROXIMITY_DEG) &
                (abs(df_fatores["coordenada_y"] - lon_c) < _PROXIMITY_DEG)
            )
            nearby = df_fatores[mask]
            fatores_near = (
                nearby["tipo_ocorrencia_descricao"]
                .dropna()
                .loc[lambda s: ~s.str.lower().str.contains("sem ocorrência|sem ocorrencia", regex=True)]
                .value_counts()
                .head(4)
                .index.tolist()
            )

        results.append({
            "trecho":      nome,
            "ocorrencias": trecho["ocorrencias"],
            "fatores":     fatores_near,
            "coincidencia": len(fatores_near) > 0,
        })

    return results


def calcular_resumo_executivo(
    identificacao: dict,
    indicadores: dict,
    fatores: list[dict],
    coincidencias: list[dict],
    disk_denuncia_resumo: str = "",
    use_llm: bool = True,
) -> dict:
    """
    Builds strategic question-answers for the executive summary.
    When use_llm=True (default), generates a human-readable narrative via Claude.
    Q2 and Q3 require FM operational data (unavailable) — returned as None.
    """
    top = identificacao.get("trechos_criticos", [])[:3]

    # Q1 — hotspot trechos (deterministic fallback)
    if top:
        partes = [f"{t['logradouro']} ({t['ocorrencias']} oc.)" for t in top]
        q1_fallback = "Os trechos mais críticos são: " + "; ".join(partes) + "."
    else:
        q1_fallback = "Nenhum trecho crítico identificado no período."

    # Q4 — factors being addressed (deterministic fallback)
    ativos = [
        f for f in fatores
        if f.get("orgao") and f["orgao"] not in ("—", "nan", "")
    ]
    if ativos:
        partes4 = [
            f"{f['fator']} → {f['orgao']} ({f['quantidade']} ocor.)"
            for f in ativos[:4]
        ]
        q4_fallback = f"{len(ativos)} fator(es) com órgão responsável: " + "; ".join(partes4) + "."
    else:
        q4_fallback = "Nenhum fator com órgão responsável identificado na área."

    bingos = [c for c in coincidencias if c["coincidencia"]]

    ranking_pos   = indicadores.get("ranking_pos")
    ranking_total = indicadores.get("ranking_total_areas")
    ranking_pct   = indicadores.get("ranking_pct")
    ranking_resumo = (
        f"{ranking_pos}º lugar entre {ranking_total} áreas FM "
        f"({ranking_pct}% das ocorrências da cidade)"
        if ranking_pos else ""
    )

    # LLM-generated narrative for the full executive summary
    narrativa_llm = None
    if use_llm:
        try:
            from llm_gen import gerar_resumo_executivo
            narrativa_llm = gerar_resumo_executivo(
                nome_area=identificacao.get("nome_area", ""),
                indicadores=indicadores,
                identificacao=identificacao,
                fatores=fatores,
                coincidencias=coincidencias,
                disk_denuncia_resumo=disk_denuncia_resumo,
            )
        except Exception as exc:
            narrativa_llm = f"[Narrativa LLM indisponível: {exc}]"

    return {
        "q1_texto":    "Quais são os trechos mais críticos da área?",
        "q1_resposta": q1_fallback,
        "q2_texto":    "O efetivo da FM cobre os pontos críticos?",
        "q2_resposta": None,
        "q3_texto":    "Quais ações foram executadas desde o último relatório?",
        "q3_resposta": None,
        "q4_texto":    "Quais fatores de incidência estão sendo tratados?",
        "q4_resposta": q4_fallback,
        "n_bingos":         len(bingos),
        "n_total_trechos":  len(coincidencias),
        "ranking_resumo":   ranking_resumo,
        "narrativa_llm":    narrativa_llm,
    }
