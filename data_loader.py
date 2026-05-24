"""Normalize every Rio public-safety source into WGS84 GeoDataFrames.

Each per-source folder under `data/` is read by globbing its `*.csv` files and
concatenating them, so new weekly uploads are picked up just by dropping another
file into the right folder. Static sources (cameras, dominio_territorial,
areas_forca shapefile) live in the same layout but only ever contain one file.

`duckdb_connection()` gives a DuckDB connection with the spatial extension
loaded and every layer registered as a view.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely import wkt
from shapely.geometry import Point

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"

WGS84 = "EPSG:4326"

# Generous bbox around Rio metro — used to drop corrupt/out-of-area coordinates
RIO_BBOX = (-44.5, -23.5, -42.5, -22.5)

# Required columns per uploadable source — validated before accepting uploads
REQUIRED_COLS: dict[str, set[str]] = {
    "ocorrencias": {"ano", "mes", "longitude", "latitude", "desc_delito"},
    "disk_denuncia": {"id_denuncia", "data_denuncia", "latitude", "longitude"},
    "fatores_urbanos": {"id_resposta_ocorrencia", "coordenada_x", "coordenada_y"},
}

# Dedup keys per source (last file wins, so re-uploads are idempotent)
DEDUP_KEYS: dict[str, str] = {
    "ocorrencias": "id_criptografado",
    "disk_denuncia": "id_denuncia",
    "fatores_urbanos": "id_resposta_ocorrencia",
}

# read_csv kwargs per uploadable source — shared by loader and upload validator
READ_KWARGS: dict[str, dict] = {
    "ocorrencias": dict(dtype={"hora": "string", "data": "string"}, low_memory=False),
    "disk_denuncia": dict(sep=";", encoding="latin1", dtype="string", low_memory=False),
    "fatores_urbanos": dict(low_memory=False),
}


def _in_rio(lon: pd.Series, lat: pd.Series) -> pd.Series:
    minx, miny, maxx, maxy = RIO_BBOX
    return lon.between(minx, maxx) & lat.between(miny, maxy)


def _to_gdf(df: pd.DataFrame, geom_col: str = "geometry") -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(df, geometry=geom_col, crs=WGS84)


def _concat_csvs(source: str) -> pd.DataFrame:
    folder = DATA / source
    files = sorted(folder.glob("*.csv"))
    if not files:
        return pd.DataFrame()
    kwargs = READ_KWARGS.get(source, {})
    frames = [pd.read_csv(f, **kwargs) for f in files]
    df = pd.concat(frames, ignore_index=True)
    key = DEDUP_KEYS.get(source)
    if key and key in df.columns:
        df = df.drop_duplicates(subset=[key], keep="last").reset_index(drop=True)
    return df


@lru_cache(maxsize=1)
def load_cameras() -> gpd.GeoDataFrame:
    df = pd.read_csv(next((DATA / "cameras").glob("*.csv")))
    df["geometry"] = df["geometry"].apply(wkt.loads)
    return _to_gdf(df)


@lru_cache(maxsize=1)
def load_ocorrencias() -> gpd.GeoDataFrame:
    df = _concat_csvs("ocorrencias")
    if df.empty:
        return _to_gdf(pd.DataFrame({"geometry": []}))
    df = df.dropna(subset=["longitude", "latitude"])
    df = df[_in_rio(df["longitude"], df["latitude"])]
    df["geometry"] = [Point(x, y) for x, y in zip(df["longitude"], df["latitude"])]
    df = df.drop(columns=["geometria"], errors="ignore")
    df["ano"] = pd.to_numeric(df["ano"], errors="coerce").astype("Int64")
    df["mes"] = pd.to_numeric(df["mes"], errors="coerce").astype("Int64")
    df["hora"] = pd.to_numeric(df["hora"], errors="coerce").astype("Int64")
    return _to_gdf(df)


@lru_cache(maxsize=1)
def load_disk_denuncia() -> gpd.GeoDataFrame:
    df = _concat_csvs("disk_denuncia")
    if df.empty:
        return _to_gdf(pd.DataFrame({"geometry": []}))
    df["latitude"] = pd.to_numeric(df["latitude"].str.replace(",", ".", regex=False), errors="coerce")
    df["longitude"] = pd.to_numeric(df["longitude"].str.replace(",", ".", regex=False), errors="coerce")
    df = df.dropna(subset=["latitude", "longitude"])
    df = df[_in_rio(df["longitude"], df["latitude"])]
    df["geometry"] = [Point(x, y) for x, y in zip(df["longitude"], df["latitude"])]
    for col in ("data_denuncia", "data_difusao", "timestamp_insercao"):
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")
    return _to_gdf(df)


@lru_cache(maxsize=1)
def load_fatores_urbanos() -> gpd.GeoDataFrame:
    df = _concat_csvs("fatores_urbanos")
    if df.empty:
        return _to_gdf(pd.DataFrame({"geometry": []}))
    # coordenada_x is latitude, coordenada_y is longitude (verified by value range)
    df = df.dropna(subset=["coordenada_x", "coordenada_y"])
    df["geometry"] = [
        Point(lon, lat) for lat, lon in zip(df["coordenada_x"], df["coordenada_y"])
    ]
    return _to_gdf(df)


@lru_cache(maxsize=1)
def load_dominio_territorial() -> gpd.GeoDataFrame:
    df = pd.read_csv(next((DATA / "dominio_territorial").glob("*.csv")))
    df["geometry"] = df["geometria"].apply(wkt.loads)
    gdf = _to_gdf(df.drop(columns=["geometria"]))
    pt = gdf.geometry.representative_point()
    return gdf[_in_rio(pt.x, pt.y)].reset_index(drop=True)


@lru_cache(maxsize=1)
def load_areas_forca() -> gpd.GeoDataFrame:
    shp = next((DATA / "areas_forca").glob("*.shp"))
    return gpd.read_file(shp).to_crs(WGS84)


LAYERS: dict[str, callable] = {
    "cameras": load_cameras,
    "ocorrencias": load_ocorrencias,
    "disk_denuncia": load_disk_denuncia,
    "fatores_urbanos": load_fatores_urbanos,
    "dominio_territorial": load_dominio_territorial,
    "areas_forca": load_areas_forca,
}


def load_all() -> dict[str, gpd.GeoDataFrame]:
    return {name: fn() for name, fn in LAYERS.items()}


def clear_cache(source: str | None = None) -> None:
    """Invalidate cached layers after files change on disk."""
    if source is None:
        for fn in LAYERS.values():
            fn.cache_clear()
    elif source in LAYERS:
        LAYERS[source].cache_clear()


def duckdb_connection():
    """Return a DuckDB connection with spatial loaded and every layer registered."""
    import duckdb

    con = duckdb.connect()
    con.execute("INSTALL spatial; LOAD spatial;")
    for name, gdf in load_all().items():
        df = pd.DataFrame(gdf.drop(columns=["geometry"]))
        df["wkt"] = gdf.geometry.to_wkt()
        con.register(f"{name}_df", df)
        con.execute(
            f"CREATE OR REPLACE VIEW {name} AS "
            f"SELECT * EXCLUDE wkt, ST_GeomFromText(wkt) AS geom FROM {name}_df"
        )
    return con


if __name__ == "__main__":
    for name, gdf in load_all().items():
        bounds = tuple(round(v, 3) for v in gdf.total_bounds) if not gdf.empty else ()
        print(f"{name:22s} {len(gdf):>8,d} rows  bbox={bounds}")
