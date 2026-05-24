"""Streamlit dashboard for Rio public-safety data."""

from __future__ import annotations

import altair as alt
import geopandas as gpd
import pandas as pd
import pydeck as pdk
import streamlit as st

import data_loader as dl

st.set_page_config(page_title="Segurança Rio", layout="wide")

RIO_VIEW = pdk.ViewState(latitude=-22.92, longitude=-43.35, zoom=10, pitch=0)

LAYER_COLORS = {
    "ocorrencias": [220, 50, 50],
    "disk_denuncia": [255, 165, 0],
    "cameras": [40, 120, 240],
    "fatores_urbanos": [120, 200, 80],
}


@st.cache_data(show_spinner="Carregando dados…")
def cached_layer(name: str) -> gpd.GeoDataFrame:
    return dl.LAYERS[name]()


def gdf_to_points(gdf: gpd.GeoDataFrame) -> pd.DataFrame:
    pts = gdf[gdf.geometry.geom_type == "Point"].copy()
    pts["lon"] = pts.geometry.x
    pts["lat"] = pts.geometry.y
    return pd.DataFrame(pts.drop(columns="geometry"))


def gdf_to_polygons(gdf: gpd.GeoDataFrame) -> pd.DataFrame:
    polys = gdf[gdf.geometry.geom_type.isin(["Polygon", "MultiPolygon"])].copy()
    polys["coordinates"] = polys.geometry.apply(
        lambda g: [list(g.exterior.coords)] if g.geom_type == "Polygon"
        else [list(p.exterior.coords) for p in g.geoms]
    )
    return pd.DataFrame(polys.drop(columns="geometry"))


def sidebar_filters(ocorr: gpd.GeoDataFrame) -> dict:
    st.sidebar.header("Camadas")
    layers = {
        "ocorrencias": st.sidebar.checkbox("Ocorrências (crimes)", value=True),
        "disk_denuncia": st.sidebar.checkbox("Disk denúncia", value=False),
        "cameras": st.sidebar.checkbox("Câmeras", value=True),
        "fatores_urbanos": st.sidebar.checkbox("Fatores urbanos", value=False),
        "areas_forca": st.sidebar.checkbox("Áreas força municipal", value=True),
        "dominio_territorial": st.sidebar.checkbox("Domínio territorial (OrCrim)", value=False),
    }

    st.sidebar.header("Filtros (ocorrências)")
    years = sorted(int(y) for y in ocorr["ano"].dropna().unique())
    sel_years = st.sidebar.multiselect("Ano", years, default=years[-3:] if len(years) >= 3 else years)

    delitos = sorted(ocorr["desc_delito"].dropna().unique())
    sel_delitos = st.sidebar.multiselect("Tipo de delito", delitos, default=[])

    sample = st.sidebar.slider("Amostra (ocorrências exibidas)", 1_000, 50_000, 10_000, step=1_000)
    return {
        "layers": layers,
        "years": sel_years,
        "delitos": sel_delitos,
        "sample": sample,
    }


def filter_ocorrencias(gdf: gpd.GeoDataFrame, years: list[int], delitos: list[str], sample: int) -> gpd.GeoDataFrame:
    out = gdf
    if years:
        out = out[out["ano"].isin(years)]
    if delitos:
        out = out[out["desc_delito"].isin(delitos)]
    if len(out) > sample:
        out = out.sample(sample, random_state=0)
    return out


def build_map(filters: dict, layers_data: dict) -> pdk.Deck:
    deck_layers = []

    if filters["layers"]["areas_forca"]:
        polys = gdf_to_polygons(layers_data["areas_forca"])
        deck_layers.append(pdk.Layer(
            "PolygonLayer", polys, get_polygon="coordinates",
            get_fill_color=[0, 100, 200, 30], get_line_color=[0, 60, 160, 200],
            line_width_min_pixels=1, pickable=True,
        ))

    if filters["layers"]["dominio_territorial"]:
        polys = gdf_to_polygons(layers_data["dominio_territorial"])
        deck_layers.append(pdk.Layer(
            "PolygonLayer", polys, get_polygon="coordinates",
            get_fill_color=[150, 0, 80, 60], get_line_color=[120, 0, 60, 200],
            line_width_min_pixels=1, pickable=True,
        ))

    for name in ("fatores_urbanos", "cameras", "disk_denuncia", "ocorrencias"):
        if filters["layers"].get(name) and name in layers_data:
            pts = gdf_to_points(layers_data[name])
            if pts.empty:
                continue
            deck_layers.append(pdk.Layer(
                "ScatterplotLayer", pts, get_position="[lon, lat]",
                get_radius=40, radius_min_pixels=2, radius_max_pixels=8,
                get_fill_color=LAYER_COLORS[name] + [160], pickable=True,
            ))

    return pdk.Deck(
        layers=deck_layers,
        initial_view_state=RIO_VIEW,
        map_style="light",
        tooltip={"text": "{desc_delito}{nome_area_fm}{nome_territorio}{tipo_ocorrencia_descricao}"},
    )


def crime_timeseries(ocorr: gpd.GeoDataFrame) -> alt.Chart:
    s = ocorr.dropna(subset=["ano", "mes"]).copy()
    s["ym"] = pd.to_datetime(
        s["ano"].astype(int).astype(str) + "-" + s["mes"].astype(int).astype(str).str.zfill(2) + "-01",
        errors="coerce",
    )
    agg = s.groupby(["ym", "desc_delito"]).size().reset_index(name="n")
    return (
        alt.Chart(agg)
        .mark_line()
        .encode(x="ym:T", y="n:Q", color="desc_delito:N", tooltip=["ym:T", "desc_delito", "n"])
        .properties(height=260)
    )


def main() -> None:
    st.title("Segurança Rio — Painel de exploração")

    ocorr = cached_layer("ocorrencias")
    filters = sidebar_filters(ocorr)

    layers_data = {
        name: cached_layer(name)
        for name, on in filters["layers"].items() if on
    }
    if "ocorrencias" in layers_data:
        layers_data["ocorrencias"] = filter_ocorrencias(
            layers_data["ocorrencias"], filters["years"], filters["delitos"], filters["sample"],
        )

    col_map, col_side = st.columns([3, 1])
    with col_map:
        st.pydeck_chart(build_map(filters, layers_data), use_container_width=True)
    with col_side:
        st.subheader("Resumo")
        for name, gdf in layers_data.items():
            st.metric(name, f"{len(gdf):,}")

    if "ocorrencias" in layers_data and not layers_data["ocorrencias"].empty:
        st.subheader("Série temporal — ocorrências filtradas")
        st.altair_chart(crime_timeseries(layers_data["ocorrencias"]), use_container_width=True)

        st.subheader("Top tipos de delito (filtrados)")
        top = (
            layers_data["ocorrencias"]["desc_delito"]
            .value_counts().head(15).rename_axis("delito").reset_index(name="n")
        )
        st.dataframe(top, use_container_width=True, hide_index=True)


if __name__ == "__main__":
    main()
