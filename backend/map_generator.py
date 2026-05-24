"""
Generates static map images (PNG) for embedding in the PDF report.
Uses matplotlib + contextily for tile-based background maps.
"""
from __future__ import annotations

import io
import base64
import warnings

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")  # non-interactive backend — safe for server use
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
from matplotlib.patches import Patch
import contextily as ctx
from shapely.geometry import Polygon as ShapelyPolygon

warnings.filterwarnings("ignore", category=UserWarning)


# ── Colour palette ────────────────────────────────────────────────────────────
HEATMAP_CMAP   = "YlOrRd"
CAMERA_COLOR   = "#1a6eb5"
POLYGON_EDGE   = "#2c2c2c"
POLYGON_FILL   = "#e8000010"  # very light fill


def _fig_to_base64(fig: plt.Figure) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
    buf.seek(0)
    encoded = base64.b64encode(buf.read()).decode("utf-8")
    plt.close(fig)
    return encoded


def gerar_mapa_hotspot(
    df_ocorrencias: pd.DataFrame,
    df_cameras: pd.DataFrame,
    polygon: ShapelyPolygon,
    nome_area: str,
    df_fatores: pd.DataFrame | None = None,
) -> str:
    """
    Renders the crime hotspot map for the report cover.
    Returns a base64-encoded PNG string.

    df_ocorrencias: already filtered by polygon and period
    df_cameras:     already filtered by polygon
    polygon:        shapely polygon of the selected area
    """
    import re

    fig, ax = plt.subplots(figsize=(10, 8))

    # ── Draw area polygon ──────────────────────────────────────────────────
    x, y = polygon.exterior.xy
    ax.fill(x, y, alpha=0.08, color="#e63900")
    ax.plot(x, y, color=POLYGON_EDGE, linewidth=1.5)

    # ── Plot crime points ──────────────────────────────────────────────────
    crimes = df_ocorrencias.dropna(subset=["longitude", "latitude"])
    if not crimes.empty:
        ax.scatter(
            crimes["longitude"],
            crimes["latitude"],
            c="#e63900",
            s=12,
            alpha=0.45,
            zorder=3,
            label="Ocorrências criminais",
        )

    # ── Plot cameras ───────────────────────────────────────────────────────
    cam_pts = []
    for _, row in df_cameras.iterrows():
        nums = re.findall(r"[-\d.]+", str(row["geometry"]))
        if len(nums) >= 2:
            cam_pts.append((float(nums[0]), float(nums[1])))

    if cam_pts:
        cam_lons, cam_lats = zip(*cam_pts)
        ax.scatter(
            cam_lons,
            cam_lats,
            c=CAMERA_COLOR,
            s=25,
            alpha=0.8,
            marker="^",
            zorder=4,
            label="Câmeras",
        )

    # ── Plot fatores urbanos overlay ───────────────────────────────────────
    if df_fatores is not None and not df_fatores.empty:
        fat = df_fatores.dropna(subset=["coordenada_x", "coordenada_y"])
        if not fat.empty:
            ax.scatter(
                fat["coordenada_y"],   # longitude column (non-standard naming)
                fat["coordenada_x"],   # latitude column
                c="#ff8c00",
                s=20,
                alpha=0.75,
                marker="s",
                zorder=3,
                label="Fatores urbanos",
            )

    # ── Basemap ────────────────────────────────────────────────────────────
    try:
        ctx.add_basemap(
            ax,
            crs="EPSG:4326",
            source=ctx.providers.CartoDB.Positron,
            zoom="auto",
            attribution=False,
        )
    except Exception:
        # If tiles fail (no internet), skip silently
        ax.set_facecolor("#f5f5f5")

    # ── Labels & legend ────────────────────────────────────────────────────
    ax.set_title(
        f"Mapa de ocorrências criminais\n{nome_area}",
        fontsize=11, fontweight="bold", pad=10,
    )
    ax.legend(loc="lower right", fontsize=8, framealpha=0.85)
    ax.set_axis_off()

    plt.tight_layout()
    return _fig_to_base64(fig)


def gerar_heatmap_temporal(heatmap_data: dict) -> str:
    """
    Renders the hour × weekday heatmap.
    heatmap_data: output of secao1.calcular_heatmap_temporal()
    Returns base64-encoded PNG.
    """
    if not heatmap_data.get("matrix"):
        fig, ax = plt.subplots(figsize=(8, 4))
        ax.text(0.5, 0.5, "Sem dados suficientes", ha="center", va="center")
        return _fig_to_base64(fig)

    grid      = heatmap_data["matrix"]   # list of 24 rows × n_days cols
    days      = heatmap_data["day_labels"]
    hours     = heatmap_data["hours"]

    matrix = np.array([[cell["count"] for cell in row] for row in grid])

    fig, ax = plt.subplots(figsize=(max(7, len(days) * 0.9), 6))
    im = ax.imshow(matrix, aspect="auto", cmap=HEATMAP_CMAP, interpolation="nearest")

    ax.set_xticks(range(len(days)))
    ax.set_xticklabels(days, fontsize=9)
    ax.set_yticks(range(len(hours)))
    ax.set_yticklabels([f"{h:02d}h" for h in hours], fontsize=7)

    ax.set_xlabel("Dia da semana", fontsize=10)
    ax.set_ylabel("Hora do dia", fontsize=10)
    ax.set_title("Distribuição de ocorrências por hora e dia da semana", fontsize=11, fontweight="bold")

    plt.colorbar(im, ax=ax, label="Nº de ocorrências", shrink=0.8)
    plt.tight_layout()
    return _fig_to_base64(fig)


def gerar_grafico_mensal(serie_mensal: list[dict]) -> str:
    """
    Renders a bar chart of monthly crime evolution.
    serie_mensal: list of {ano, mes, total}
    Returns base64-encoded PNG.
    """
    if not serie_mensal:
        fig, ax = plt.subplots(figsize=(8, 3))
        ax.text(0.5, 0.5, "Sem dados", ha="center", va="center")
        return _fig_to_base64(fig)

    df = pd.DataFrame(serie_mensal)
    df["periodo"] = df.apply(
        lambda r: f"{int(r['ano'])}/{int(r['mes']):02d}", axis=1
    )

    fig, ax = plt.subplots(figsize=(max(8, len(df) * 0.4), 3.5))
    bars = ax.bar(df["periodo"], df["total"], color="#e63900", alpha=0.8, width=0.7)

    ax.set_xlabel("Mês / Ano", fontsize=9)
    ax.set_ylabel("Ocorrências", fontsize=9)
    ax.set_title("Evolução mensal de ocorrências", fontsize=11, fontweight="bold")
    ax.tick_params(axis="x", rotation=45, labelsize=7)
    ax.yaxis.grid(True, alpha=0.3)
    ax.set_axisbelow(True)

    plt.tight_layout()
    return _fig_to_base64(fig)
