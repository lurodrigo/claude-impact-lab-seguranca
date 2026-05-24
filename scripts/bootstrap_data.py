"""One-shot: split `dados/` into `data/` (bootstrap snapshot) + `next_inputs/` (simulated weekly drops).

Run once to prepare the new on-disk layout. Re-running wipes `data/` and `next_inputs/` and
rebuilds them from `dados/`. Existing `dados/` files are not modified.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DADOS = ROOT / "dados"
OUTROS = DADOS / "outros dados"
SHAPES_SRC = ROOT / "sh_area_forca"
DATA = ROOT / "data"
NEXT = ROOT / "next_inputs"


def _reset(folder: Path) -> None:
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir(parents=True)


def _write_chunks(df: pd.DataFrame, folder: Path, *, prefix: str = "week", n: int = 4, **to_csv_kwargs) -> list[int]:
    folder.mkdir(parents=True, exist_ok=True)
    if df.empty:
        return []
    chunks = [c for c in (df.iloc[i::n] for i in range(n)) if not c.empty]
    counts = []
    for i, chunk in enumerate(chunks, start=1):
        chunk.to_csv(folder / f"{prefix}_{i}.csv", index=False, **to_csv_kwargs)
        counts.append(len(chunk))
    return counts


def bootstrap_ocorrencias() -> None:
    src = DADOS / "df_ocorrencias_tratado - Extração 1 .csv"
    df = pd.read_csv(src, dtype={"hora": "string", "data": "string"}, low_memory=False)
    df["ano"] = pd.to_numeric(df["ano"], errors="coerce").astype("Int64")
    df["mes"] = pd.to_numeric(df["mes"], errors="coerce").astype("Int64")
    valid = df.dropna(subset=["ano", "mes"])
    max_year = int(valid["ano"].max())
    max_month = int(valid[valid["ano"] == max_year]["mes"].max())
    last_mask = (df["ano"] == max_year) & (df["mes"] == max_month)

    hist = df[~last_mask]
    last = df[last_mask]

    (DATA / "ocorrencias").mkdir(parents=True, exist_ok=True)
    hist.to_csv(DATA / "ocorrencias" / "historical.csv", index=False)
    weekly = _write_chunks(last, NEXT / "ocorrencias")
    print(f"ocorrencias: historical={len(hist)}, last_month={max_year}-{max_month:02d} ({len(last)}) split into {weekly}")


def bootstrap_disk_denuncia() -> None:
    src = DADOS / "disk_denuncia_clean.csv"
    df = pd.read_csv(src, sep=";", encoding="latin1", dtype="string", low_memory=False)
    parsed = pd.to_datetime(df["data_denuncia"], errors="coerce")
    valid = parsed.dropna()
    max_dt = valid.max()
    last_period = max_dt.to_period("M")
    last_mask = parsed.dt.to_period("M") == last_period

    hist = df[~last_mask]
    last = df[last_mask].copy()
    last_parsed = parsed[last_mask]

    (DATA / "disk_denuncia").mkdir(parents=True, exist_ok=True)
    hist.to_csv(DATA / "disk_denuncia" / "historical.csv", index=False, sep=";", encoding="latin1")

    # Group last month by ISO week into weekly files (up to 4)
    (NEXT / "disk_denuncia").mkdir(parents=True, exist_ok=True)
    weeks = last_parsed.dt.isocalendar().week
    week_order = sorted(weeks.dropna().unique())[:4]
    counts = []
    for i, wk in enumerate(week_order, start=1):
        chunk = last[weeks == wk]
        chunk.to_csv(NEXT / "disk_denuncia" / f"week_{i}.csv", index=False, sep=";", encoding="latin1")
        counts.append(len(chunk))
    print(f"disk_denuncia: historical={len(hist)}, last_month={last_period} ({len(last)}) split by ISO week into {counts}")


def bootstrap_fatores_urbanos() -> None:
    src = DADOS / "fatores_urbanos.csv"
    df = pd.read_csv(src, low_memory=False)
    df = df.sample(frac=1.0, random_state=0).reset_index(drop=True)
    cut = int(len(df) * 0.75)
    initial = df.iloc[:cut]
    remainder = df.iloc[cut:]

    (DATA / "fatores_urbanos").mkdir(parents=True, exist_ok=True)
    initial.to_csv(DATA / "fatores_urbanos" / "initial.csv", index=False)
    weekly = _write_chunks(remainder, NEXT / "fatores_urbanos")
    print(f"fatores_urbanos: initial={len(initial)}, remainder={len(remainder)} split into {weekly}")


def copy_static() -> None:
    # cameras
    (DATA / "cameras").mkdir(parents=True, exist_ok=True)
    shutil.copy(DADOS / "cameras_areas_fm.csv", DATA / "cameras" / "cameras_areas_fm.csv")

    # dominio territorial
    (DATA / "dominio_territorial").mkdir(parents=True, exist_ok=True)
    shutil.copy(OUTROS / "dominio_territorial - Extração 1.csv",
                DATA / "dominio_territorial" / "dominio_territorial.csv")

    # areas_forca shapefile (+ sidecars)
    (DATA / "areas_forca").mkdir(parents=True, exist_ok=True)
    for f in SHAPES_SRC.iterdir():
        shutil.copy(f, DATA / "areas_forca" / f.name)

    print("static: cameras, dominio_territorial, areas_forca copied")


def main() -> None:
    _reset(DATA)
    _reset(NEXT)
    bootstrap_ocorrencias()
    bootstrap_disk_denuncia()
    bootstrap_fatores_urbanos()
    copy_static()


if __name__ == "__main__":
    main()
