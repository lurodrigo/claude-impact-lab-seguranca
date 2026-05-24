"""
Loads disk_denuncia_classified.numbers and provides per-polygon aggregation.
Reading from the .numbers file directly as instructed; computation of the
classification columns will be integrated later.
"""
from __future__ import annotations

import os
import pandas as pd
from functools import lru_cache
from collections import Counter

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NUMBERS_PATH = os.path.join(BASE_DIR, "data", "disk_denuncia", "disk_denuncia_classified.numbers")


@lru_cache(maxsize=1)
def load_disk_denuncia_classified() -> pd.DataFrame:
    from numbers_parser import Document

    doc = Document(NUMBERS_PATH)
    sheet = doc.sheets[0]
    table = sheet.tables[0]
    rows = table.rows(values_only=True)

    header = [str(h) if h is not None else f"col_{i}" for i, h in enumerate(rows[0])]
    data = [list(r) for r in rows[1:]]
    df = pd.DataFrame(data, columns=header)

    df["latitude"]  = pd.to_numeric(df["latitude"],  errors="coerce")
    df["longitude"] = pd.to_numeric(df["longitude"], errors="coerce")
    return df


def _top_values(series: pd.Series, n: int = 5, exclude: tuple = ("Indeterminado", "None", "nan", "")) -> list[str]:
    counts = Counter(
        str(v).strip()
        for v in series.dropna()
        if str(v).strip() not in exclude
    )
    return [v for v, _ in counts.most_common(n)]


def _detail_list(series: pd.Series, n: int = 5) -> list[str]:
    """Collect unique non-null detail strings (short-ish ones)."""
    seen, result = set(), []
    for v in series.dropna():
        s = str(v).strip()
        if s and s.lower() not in ("none", "nan", "indeterminado") and len(s) < 300:
            if s not in seen:
                seen.add(s)
                result.append(s)
        if len(result) >= n:
            break
    return result


def aggregar_disk_denuncia_por_area(polygon) -> dict:
    """
    Filter disk_denuncia records that fall inside `polygon` and return
    aggregated stats for LLM summarisation.
    """
    df = load_disk_denuncia_classified()
    df_valid = df.dropna(subset=["latitude", "longitude"])

    if df_valid.empty:
        return {"total_denuncias": 0}

    # Bounding-box pre-filter
    minx, miny, maxx, maxy = polygon.bounds
    mask_bb = (
        (df_valid["longitude"] >= minx) & (df_valid["longitude"] <= maxx) &
        (df_valid["latitude"]  >= miny) & (df_valid["latitude"]  <= maxy)
    )
    df_bb = df_valid[mask_bb]

    if df_bb.empty:
        return {"total_denuncias": 0}

    from shapely.geometry import Point as _Point
    inside = df_bb.apply(
        lambda r: polygon.contains(_Point(r["longitude"], r["latitude"])), axis=1
    )
    df_area = df_bb[inside].copy()

    if df_area.empty:
        return {"total_denuncias": 0}

    # Only use rows that have at least one non-Indeterminado classification
    classified_mask = df_area["desc_delito"].apply(
        lambda v: str(v).strip() not in ("Indeterminado", "None", "nan", "")
    )
    df_classified = df_area[classified_mask]

    col_classe = "assuntos.classe" if "assuntos.classe" in df_area.columns else "classe"

    n_rotas = int((df_classified["rotas_fuga"] == "Sim").sum()) if "rotas_fuga" in df_classified.columns else 0
    n_recep = int((df_classified["pontos_receptacao"] == "Sim").sum()) if "pontos_receptacao" in df_classified.columns else 0
    n_org   = int((df_classified["influencia_org_criminosas"] == "Sim").sum()) if "influencia_org_criminosas" in df_classified.columns else 0

    return {
        "total_denuncias":      len(df_area),
        "total_classificadas":  len(df_classified),
        "top_classes":          _top_values(df_area[col_classe]) if col_classe in df_area.columns else [],
        "top_desc_delito":      _top_values(df_classified["desc_delito"]) if "desc_delito" in df_classified.columns else [],
        "top_modus_operandi":   _top_values(df_classified["modus_operandi"]) if "modus_operandi" in df_classified.columns else [],
        "n_rotas_fuga":         n_rotas,
        "rotas_fuga_detalhes":  _detail_list(df_classified["rotas_fuga_detalhes"]) if "rotas_fuga_detalhes" in df_classified.columns and n_rotas > 0 else [],
        "n_receptacao":         n_recep,
        "receptacao_detalhes":  _detail_list(df_classified["pontos_receptacao_detalhes"]) if "pontos_receptacao_detalhes" in df_classified.columns and n_recep > 0 else [],
        "n_org_criminosas":     n_org,
        "org_criminosas_detalhes": _detail_list(df_classified["influencia_org_criminosas_detalhes"]) if "influencia_org_criminosas_detalhes" in df_classified.columns and n_org > 0 else [],
    }
