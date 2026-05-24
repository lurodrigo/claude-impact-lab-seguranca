"""Normalize every Rio public-safety source into WGS84 GeoDataFrames.

All loaders return a `geopandas.GeoDataFrame` in EPSG:4326. `duckdb_connection()`
gives a DuckDB connection with the spatial extension loaded and every table
registered as a view, so you can join across sources with SQL.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely import wkt
from shapely.geometry import Point

ROOT = Path(__file__).resolve().parent
DADOS = ROOT / "dados"
OUTROS = DADOS / "outros dados"
SHAPES = ROOT / "sh_area_forca"
RELINTS = ROOT / "relints"

WGS84 = "EPSG:4326"

# Generous bbox around Rio metro — used to drop corrupt/out-of-area coordinates
RIO_BBOX = (-44.5, -23.5, -42.5, -22.5)  # (minx, miny, maxx, maxy)


def _in_rio(lon: pd.Series, lat: pd.Series) -> pd.Series:
    minx, miny, maxx, maxy = RIO_BBOX
    return lon.between(minx, maxx) & lat.between(miny, maxy)


def _to_gdf(df: pd.DataFrame, geom_col: str = "geometry") -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(df, geometry=geom_col, crs=WGS84)


@lru_cache(maxsize=1)
def load_cameras() -> gpd.GeoDataFrame:
    df = pd.read_csv(DADOS / "cameras_areas_fm.csv")
    df["geometry"] = df["geometry"].apply(wkt.loads)
    return _to_gdf(df)


@lru_cache(maxsize=1)
def load_ocorrencias() -> gpd.GeoDataFrame:
    df = pd.read_csv(
        DADOS / "df_ocorrencias_tratado - Extração 1 .csv",
        dtype={"hora": "string", "data": "string"},
        low_memory=False,
    )
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
    df = pd.read_csv(
        DADOS / "disk_denuncia_clean.csv",
        sep=";",
        encoding="latin1",
        dtype="string",
        low_memory=False,
    )
    # dtype=string skips pandas' decimal=',' handling — convert manually
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
    df = pd.read_csv(DADOS / "fatores_urbanos.csv", low_memory=False)
    # coordenada_x is latitude, coordenada_y is longitude (verified by value range)
    df = df.dropna(subset=["coordenada_x", "coordenada_y"])
    df["geometry"] = [
        Point(lon, lat) for lat, lon in zip(df["coordenada_x"], df["coordenada_y"])
    ]
    return _to_gdf(df)


@lru_cache(maxsize=1)
def load_dominio_territorial() -> gpd.GeoDataFrame:
    df = pd.read_csv(OUTROS / "dominio_territorial - Extração 1.csv")
    df["geometry"] = df["geometria"].apply(wkt.loads)
    gdf = _to_gdf(df.drop(columns=["geometria"]))
    # Drop polygons whose representative point is outside Rio
    pt = gdf.geometry.representative_point()
    return gdf[_in_rio(pt.x, pt.y)].reset_index(drop=True)


@lru_cache(maxsize=1)
def load_areas_forca() -> gpd.GeoDataFrame:
    return gpd.read_file(SHAPES / "areas_forca_municipal.shp").to_crs(WGS84)


@lru_cache(maxsize=1)
def load_cpsr() -> pd.DataFrame:
    return pd.read_excel(OUTROS / "CPSR_2020_2022_2024.xlsx")


@lru_cache(maxsize=1)
def load_data_dictionary() -> dict[str, pd.DataFrame]:
    return pd.read_excel(DADOS / "Dicionário de dados.xlsx", sheet_name=None)


@lru_cache(maxsize=1)
def load_relints() -> pd.DataFrame:
    from docx import Document

    rows = []
    for path in sorted(RELINTS.glob("*.docx")):
        doc = Document(path)
        text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
        rows.append({"file": path.name, "text": text})
    return pd.DataFrame(rows)


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
        print(f"{name:22s} {len(gdf):>8,d} rows  bbox={tuple(round(v, 3) for v in gdf.total_bounds)}")
