"""
Orchestrator: takes input parameters, runs all calculations, and returns
a complete report context dict ready for the Jinja2 template.
"""
from __future__ import annotations

import os
import sys

# Allow running from the backend/ directory directly
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd

from config import DEFAULT_ANO_INICIO, DEFAULT_ANO_FIM
from data_loader import (
    load_ocorrencias, load_fatores, load_cameras, load_dominio, load_cpsr
)
from spatial import (
    get_area_by_fid, get_area_names,
    filter_ocorrencias, filter_fatores, filter_cameras,
    filter_dominio, filter_cpsr,
)
from sections.secao1 import (
    calcular_identificacao,
    calcular_indicadores,
    calcular_distribuicao_tipos,
    calcular_heatmap_temporal,
)
from sections.secao4 import calcular_fatores, calcular_psr, calcular_cameras, calcular_plano_de_acao
from sections.secao5 import calcular_coincidencias, calcular_resumo_executivo
from map_generator import (
    gerar_mapa_hotspot,
    gerar_heatmap_temporal,
    gerar_grafico_mensal,
)


def _get_nome_area_fm(df_cameras_area: pd.DataFrame, fallback: str) -> str:
    """Resolve display name from cameras data; falls back to shapefile nome."""
    if not df_cameras_area.empty and "nome_area_fm" in df_cameras_area.columns:
        return df_cameras_area["nome_area_fm"].mode().iloc[0]
    return fallback


def _calcular_ranking(
    fid_selecionado: int,
    polygon_selecionado,
    df_ocorrencias_full: pd.DataFrame,
    ano_inicio: int,
    ano_fim: int,
) -> dict:
    """
    Computes ranking of selected area among all FM areas by crime count.
    Returns {pos, total_areas, pct}.
    """
    from spatial import load_areas, filter_ocorrencias as _fo

    areas = load_areas()
    df_p  = df_ocorrencias_full[
        (df_ocorrencias_full["ano"] >= ano_inicio) &
        (df_ocorrencias_full["ano"] <= ano_fim)
    ]

    contagens = {}
    for area in areas:
        filtered = _fo(df_p, area["geometry"])
        contagens[area["fid"]] = len(filtered)

    total_areas  = len(contagens)
    sorted_areas = sorted(contagens.items(), key=lambda x: -x[1])
    pos          = next((i + 1 for i, (fid, _) in enumerate(sorted_areas) if fid == fid_selecionado), None)
    total_sel    = contagens.get(fid_selecionado, 0)
    total_all    = sum(contagens.values())
    pct          = round(total_sel / total_all * 100, 1) if total_all else 0

    return {"pos": pos, "total_areas": total_areas, "pct": pct}


# ─────────────────────────────────────────────────────────────────────────────

def gerar_contexto_relatorio(
    shapefile_fid: int,
    ano_inicio: int = DEFAULT_ANO_INICIO,
    ano_fim:    int = DEFAULT_ANO_FIM,
    mes_referencia: str = "",
    gerar_mapas: bool = True,
) -> dict:
    """
    Main entry point.

    Returns a dict consumed directly by the Jinja2 template.
    All heavy computation happens here.

    Parameters
    ----------
    shapefile_fid   : fid from areas_forca_municipal.shp
    ano_inicio      : first year of the crime analysis window
    ano_fim         : last year of the crime analysis window
    mes_referencia  : e.g. "Maio 2026" — displayed in the report header
    gerar_mapas     : set False to skip matplotlib rendering (useful for unit tests)
    """
    # ── 1. Load area geometry ─────────────────────────────────────────────
    area = get_area_by_fid(shapefile_fid)
    if area is None:
        raise ValueError(f"Área com fid={shapefile_fid} não encontrada no shapefile.")
    polygon    = area["geometry"]
    nome_shp   = area["nome"]

    # ── 2. Load raw data ──────────────────────────────────────────────────
    df_oc_full  = load_ocorrencias()
    df_fat_full = load_fatores()
    df_cam_full = load_cameras()
    df_dom_full = load_dominio()
    df_cpsr_full= load_cpsr()

    # ── 3. Spatial filter ────────────────────────────────────────────────
    df_oc   = filter_ocorrencias(df_oc_full,  polygon)
    df_fat  = filter_fatores(df_fat_full,     polygon)
    df_cam  = filter_cameras(df_cam_full,     polygon)
    df_cpsr = filter_cpsr(df_cpsr_full,       polygon)
    dominios= filter_dominio(df_dom_full,     polygon)

    nome_area = _get_nome_area_fm(df_cam, nome_shp)

    # ── 4. Section calculations ──────────────────────────────────────────

    # Seção 1
    identificacao = calcular_identificacao(df_oc, nome_area, dominios, df_fatores=df_fat)
    indicadores   = calcular_indicadores(df_oc, ano_inicio, ano_fim)
    tipos         = calcular_distribuicao_tipos(df_oc, ano_inicio, ano_fim)
    temporal      = calcular_heatmap_temporal(df_oc, ano_inicio, ano_fim)

    # Ranking (requires iterating all areas — can be slow first run)
    ranking = _calcular_ranking(shapefile_fid, polygon, df_oc_full, ano_inicio, ano_fim)
    indicadores["ranking_pos"] = ranking["pos"]
    indicadores["ranking_pct"] = ranking["pct"]
    indicadores["ranking_total_areas"] = ranking["total_areas"]

    # Seção 4
    fatores = calcular_fatores(df_fat)
    psr     = calcular_psr(df_cpsr)
    cameras = calcular_cameras(df_cam)
    plano   = calcular_plano_de_acao(fatores)

    # Seção 5 — deterministic cross-reference
    df_oc_periodo = df_oc[
        (df_oc["ano"] >= ano_inicio) & (df_oc["ano"] <= ano_fim)
    ]
    coincidencias  = calcular_coincidencias(df_oc_periodo, df_fat, identificacao["trechos_criticos"])
    resumo_exec    = calcular_resumo_executivo(identificacao, indicadores, fatores, coincidencias)

    # ── 5. Map images ────────────────────────────────────────────────────
    img_mapa_hotspot  = ""
    img_heatmap       = ""
    img_serie_mensal  = ""

    if gerar_mapas:
        img_mapa_hotspot = gerar_mapa_hotspot(df_oc_periodo, df_cam, polygon, nome_area, df_fat)
        img_heatmap      = gerar_heatmap_temporal(temporal)
        img_serie_mensal = gerar_grafico_mensal(indicadores["serie_mensal"])

    # ── 6. Assemble context ──────────────────────────────────────────────
    return {
        "meta": {
            "nome_area":       nome_area,
            "periodo_criminal": f"{ano_inicio}–{ano_fim}",
            "mes_referencia":  mes_referencia or f"{ano_fim}",
            "shapefile_fid":   shapefile_fid,
        },
        "identificacao":   identificacao,
        "indicadores":     indicadores,
        "tipos":           tipos,
        "temporal":        temporal,
        "fatores":         fatores,
        "psr":             psr,
        "cameras":         cameras,
        "dominios":        dominios,
        "plano":           plano,
        "coincidencias":   coincidencias,
        "resumo_exec":     resumo_exec,
        # base64 PNG images
        "img_mapa_hotspot":  img_mapa_hotspot,
        "img_heatmap":       img_heatmap,
        "img_serie_mensal":  img_serie_mensal,
    }


def listar_areas() -> list[dict]:
    """Returns available FM areas for the UI selection dropdown."""
    return get_area_names()
