"""
Spatial filtering: loads the FM shapefile and provides point-in-polygon
filtering for all dataset types.
"""
from __future__ import annotations

import re
import shapefile
import pandas as pd
from shapely.geometry import Point, shape
from shapely.ops import unary_union
from typing import Optional

from config import PATHS


# ── Shapefile loader ──────────────────────────────────────────────────────────

def load_areas() -> list[dict]:
    """Return all FM areas from the shapefile as a list of dicts with geometry."""
    sf = shapefile.Reader(PATHS["shapefile"], encoding="utf-8")
    fields = [f[0] for f in sf.fields[1:]]
    areas = []
    for sr in sf.shapeRecords():
        rec = dict(zip(fields, sr.record))
        # shapefile shapes → shapely geometry
        geom = shape(sr.shape.__geo_interface__)
        areas.append({
            "fid":      rec["fid"],
            "nome":     rec["nome_subar"],
            "geometry": geom,
        })
    return areas


def get_area_by_fid(fid: int) -> Optional[dict]:
    for area in load_areas():
        if area["fid"] == fid:
            return area
    return None


def get_area_names() -> list[dict]:
    """Return list of {fid, nome} for UI selection."""
    return [{"fid": a["fid"], "nome": a["nome"]} for a in load_areas()]


# ── Generic point filter ──────────────────────────────────────────────────────

def filter_points_in_polygon(
    df: pd.DataFrame,
    polygon,
    lon_col: str,
    lat_col: str,
) -> pd.DataFrame:
    """
    Keep only rows where (lon_col, lat_col) fall inside `polygon`.
    Uses bounding-box pre-filter + vectorised contains for speed.
    """
    df = df.copy()
    df[lon_col] = pd.to_numeric(df[lon_col], errors="coerce")
    df[lat_col] = pd.to_numeric(df[lat_col], errors="coerce")
    df = df.dropna(subset=[lon_col, lat_col])

    # Fast bounding-box pre-filter (eliminates most rows with no geometry calls)
    minx, miny, maxx, maxy = polygon.bounds
    bbox_mask = (
        (df[lon_col] >= minx) & (df[lon_col] <= maxx) &
        (df[lat_col] >= miny) & (df[lat_col] <= maxy)
    )
    df_bbox = df[bbox_mask]

    if df_bbox.empty:
        return df_bbox

    # Exact polygon containment only on bbox survivors
    prepared_poly = polygon  # shapely.prepared.prep() would help for many points
    from shapely.geometry import Point as _Point
    mask = df_bbox.apply(
        lambda r: prepared_poly.contains(_Point(r[lon_col], r[lat_col])),
        axis=1,
    )
    return df_bbox[mask].copy()


# ── Dataset-specific filters ─────────────────────────────────────────────────

def filter_ocorrencias(df: pd.DataFrame, polygon) -> pd.DataFrame:
    return filter_points_in_polygon(df, polygon, "longitude", "latitude")


def filter_fatores(df: pd.DataFrame, polygon) -> pd.DataFrame:
    # In fatores_urbanos: coordenada_x stores latitude (-22.x) and
    # coordenada_y stores longitude (-43.x) — column names are non-standard.
    return filter_points_in_polygon(df, polygon, lon_col="coordenada_y", lat_col="coordenada_x")


def filter_cameras(df: pd.DataFrame, polygon) -> pd.DataFrame:
    """Camera geometry is stored as WKT POINT(lon lat)."""
    df = df.copy()

    def parse_point(wkt: str):
        nums = re.findall(r"[-\d.]+", str(wkt))
        if len(nums) >= 2:
            return float(nums[0]), float(nums[1])
        return None, None

    df[["_lon", "_lat"]] = df["geometry"].apply(
        lambda g: pd.Series(parse_point(g))
    )
    result = filter_points_in_polygon(df, polygon, "_lon", "_lat")
    return result.drop(columns=["_lon", "_lat"])


def filter_cpsr(df: pd.DataFrame, polygon) -> pd.DataFrame:
    return filter_points_in_polygon(df, polygon, "Longitude", "Latitude")


def filter_dominio(df: pd.DataFrame, polygon, buffer_degrees: float = 0.015) -> list[dict]:
    """
    Return orcrim groups whose territory intersects OR is within buffer_degrees
    of the selected area polygon.

    buffer_degrees=0.015 ≈ 1.5 km — captures communities that directly
    influence crime patterns in the area even without direct overlap.
    Results are tagged with "tipo": "intersecta" or "proximidade".
    """
    from shapely import wkt as shapely_wkt

    buffered = polygon.buffer(buffer_degrees)
    results = []
    seen = set()

    for _, row in df.iterrows():
        try:
            geom = shapely_wkt.loads(str(row["geometria"]).strip())
            nome   = str(row["nome_territorio"]).strip()
            orcrim = str(row["dominio_orcrim"]).strip()

            if polygon.intersects(geom):
                tipo = "intersecta"
            elif buffered.intersects(geom):
                tipo = "proximidade"
            else:
                continue

            key = (nome, orcrim)
            if key not in seen:
                seen.add(key)
                results.append({"nome": nome, "orcrim": orcrim, "tipo": tipo})
        except Exception:
            continue

    # Sort: direct intersections first, then by proximity
    results.sort(key=lambda x: (0 if x["tipo"] == "intersecta" else 1, x["orcrim"]))
    return results
