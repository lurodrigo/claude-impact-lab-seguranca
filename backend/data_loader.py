"""
Loads all raw datasets into pandas DataFrames once, caching in memory.
"""
from __future__ import annotations

import os
import pandas as pd
from functools import lru_cache

from config import PATHS


_DIA_SEMANA_MAP = {
    # Portuguese day names → int (1=Dom … 7=Sáb, matching config.DIAS_SEMANA)
    "domingo": 1, "segunda": 2, "terca": 3, "terça": 3,
    "quarta": 4, "quinta": 5, "sexta": 6, "sabado": 7, "sábado": 7,
}


@lru_cache(maxsize=1)
def load_ocorrencias() -> pd.DataFrame:
    df = pd.read_csv(PATHS["ocorrencias"], encoding="utf-8-sig", low_memory=False)
    df["ano"]       = pd.to_numeric(df["ano"],       errors="coerce")
    df["mes"]       = pd.to_numeric(df["mes"],       errors="coerce")
    df["latitude"]  = pd.to_numeric(df["latitude"],  errors="coerce")
    df["longitude"] = pd.to_numeric(df["longitude"], errors="coerce")

    # hora: stored as "HH:MM:SS" — extract integer hour
    df["hora"] = (
        df["hora"]
        .astype(str)
        .str.extract(r"^(\d{1,2}):", expand=False)
        .pipe(pd.to_numeric, errors="coerce")
    )

    # dia_semana: stored as Portuguese day name — map to 1-7
    df["dia_semana"] = (
        df["dia_semana"]
        .astype(str)
        .str.strip()
        .str.lower()
        .map(_DIA_SEMANA_MAP)
    )

    return df


@lru_cache(maxsize=1)
def load_fatores() -> pd.DataFrame:
    df = pd.read_csv(PATHS["fatores"], encoding="utf-8-sig", low_memory=False)
    df["coordenada_x"] = pd.to_numeric(df["coordenada_x"], errors="coerce")
    df["coordenada_y"] = pd.to_numeric(df["coordenada_y"], errors="coerce")
    return df


@lru_cache(maxsize=1)
def load_cameras() -> pd.DataFrame:
    return pd.read_csv(PATHS["cameras"], encoding="utf-8-sig", low_memory=False)


@lru_cache(maxsize=1)
def load_dominio() -> pd.DataFrame:
    for enc in ["utf-8-sig", "latin-1", "cp1252"]:
        try:
            return pd.read_csv(PATHS["dominio"], encoding=enc, low_memory=False)
        except UnicodeDecodeError:
            continue
    raise RuntimeError("Could not decode dominio_territorial CSV")


@lru_cache(maxsize=1)
def load_cpsr() -> pd.DataFrame:
    """
    Reads the CPSR census xlsx (23k rows × 167 cols).
    On first run it converts to parquet for fast subsequent loads (~30s → <1s).
    """
    cache_path = PATHS["cpsr"].replace(".xlsx", ".parquet")
    if os.path.exists(cache_path):
        df = pd.read_parquet(cache_path)
    else:
        import warnings
        warnings.filterwarnings("ignore", category=UserWarning)
        df = pd.read_excel(PATHS["cpsr"], sheet_name="Censo_histórico", engine="openpyxl")
        # Stringify mixed-type object columns so pyarrow can serialise them
        for col in df.columns:
            if df[col].dtype == object:
                df[col] = df[col].astype(str)
        df.to_parquet(cache_path, index=False)
    df["Latitude"]  = pd.to_numeric(df["Latitude"],  errors="coerce")
    df["Longitude"] = pd.to_numeric(df["Longitude"], errors="coerce")
    return df


def clear_cache():
    """Call if source files change during a session."""
    load_ocorrencias.cache_clear()
    load_fatores.cache_clear()
    load_cameras.cache_clear()
    load_dominio.cache_clear()
    load_cpsr.cache_clear()
