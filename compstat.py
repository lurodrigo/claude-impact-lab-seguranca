"""CompStat tab — weekly analytical readout over the dashboard data.

Six sections, in order:
  1. Resumo Executivo        — live metrics + placeholder narrative
  2. Mapa de Calor           — pydeck HeatmapLayer of Roubo/Furto
  3. Análise Temporal        — DOW × hora heatmap + crime-band chart
  4. Dinâmica Criminal       — disk_denuncia stats + RELINTs list + IA placeholder
  5. Painel de Coincidências — FM-area ranking (crimes / cameras)
  6. Plano de Ação           — pre-populated placeholder table

`render_compstat_panel(cached_layer)` is the entry point; the caller passes
the Streamlit-cached loader from app.py so all tabs share one cache.
"""

from __future__ import annotations

from typing import Callable

import altair as alt
import geopandas as gpd
import pandas as pd
import pydeck as pdk
import streamlit as st

RIO_VIEW = pdk.ViewState(latitude=-22.92, longitude=-43.35, zoom=10, pitch=0)

PERIOD_OPTIONS = ["Últimos 7 dias", "Últimos 30 dias", "Últimos 90 dias", "Tudo"]
PERIOD_DAYS = {"Últimos 7 dias": 7, "Últimos 30 dias": 30, "Últimos 90 dias": 90}

HORA_BANDS = [
    (0, 6, "madrugada"),
    (6, 12, "manhã"),
    (12, 18, "tarde"),
    (18, 24, "noite"),
]


# ---------- period filter ----------

def _reference_dates(ocorr: gpd.GeoDataFrame, disk: gpd.GeoDataFrame) -> tuple[pd.Period | None, pd.Timestamp | None]:
    ref_month = None
    if not ocorr.empty:
        ym = pd.PeriodIndex.from_fields(
            year=ocorr["ano"].dropna().astype(int),
            month=ocorr["mes"].dropna().astype(int),
            freq="M",
        ) if hasattr(pd.PeriodIndex, "from_fields") else None
        if ym is not None and len(ym):
            ref_month = ym.max()
        else:
            valid = ocorr.dropna(subset=["ano", "mes"])
            if not valid.empty:
                ref_month = pd.Period(year=int(valid["ano"].max()),
                                      month=int(valid[valid["ano"] == valid["ano"].max()]["mes"].max()),
                                      freq="M")
    ref_dt = None
    if not disk.empty and "data_denuncia" in disk.columns:
        dts = pd.to_datetime(disk["data_denuncia"], errors="coerce").dropna()
        if not dts.empty:
            ref_dt = dts.max()
    return ref_month, ref_dt


def period_filter(ocorr: gpd.GeoDataFrame, disk: gpd.GeoDataFrame) -> dict:
    label = st.selectbox("Janela de análise", PERIOD_OPTIONS, index=1)
    ref_month, ref_dt = _reference_dates(ocorr, disk)

    ocorr_filtered = ocorr
    disk_filtered = disk

    if label != "Tudo":
        days = PERIOD_DAYS[label]
        months = max(1, days // 30) if days >= 30 else 1

        if ref_month is not None:
            start_month = ref_month - (months - 1)
            mask = ocorr["ano"].notna() & ocorr["mes"].notna()
            if mask.any():
                ym = pd.PeriodIndex.from_fields(
                    year=ocorr.loc[mask, "ano"].astype(int),
                    month=ocorr.loc[mask, "mes"].astype(int),
                    freq="M",
                )
                keep_idx = ocorr.loc[mask].index[(ym >= start_month) & (ym <= ref_month)]
                ocorr_filtered = ocorr.loc[keep_idx]

        if ref_dt is not None:
            cutoff = ref_dt - pd.Timedelta(days=days)
            dts = pd.to_datetime(disk["data_denuncia"], errors="coerce")
            disk_filtered = disk[(dts >= cutoff) & (dts <= ref_dt)]

    cap = f"Referência: ocorrências até {ref_month}" if ref_month else "Sem ocorrências no período"
    if ref_dt is not None:
        cap += f" · denúncias até {ref_dt.date()}"
    st.caption(cap)

    return {"label": label, "ocorrencias": ocorr_filtered, "disk_denuncia": disk_filtered}


# ---------- §1 Resumo Executivo ----------

def section_executive(ocorr: gpd.GeoDataFrame, disk: gpd.GeoDataFrame) -> None:
    st.header("1. Resumo Executivo")
    st.caption("Perguntas norteadoras respondidas automaticamente para subsidiar a reunião CompStat.")

    cols = st.columns(6)
    cols[0].metric("Ocorrências", f"{len(ocorr):,}")

    top_delito = ocorr["desc_delito"].mode().iat[0] if not ocorr.empty and ocorr["desc_delito"].notna().any() else "—"
    cols[1].metric("Delito + frequente", top_delito if len(top_delito) <= 20 else top_delito[:18] + "…",
                   help=top_delito if isinstance(top_delito, str) else None)

    hora_peak = "—"
    if not ocorr.empty and ocorr["hora"].notna().any():
        h = int(ocorr["hora"].dropna().mode().iat[0])
        hora_peak = f"{h:02d}h"
    cols[2].metric("Hora de pico", hora_peak)

    aisp_top = "—"
    if not ocorr.empty and "aisp" in ocorr.columns and ocorr["aisp"].notna().any():
        aisp_top = str(int(ocorr["aisp"].mode().iat[0]))
    cols[3].metric("AISP + crítica", aisp_top)

    cols[4].metric("Denúncias", f"{len(disk):,}")

    classe_top = "—"
    if not disk.empty and "assuntos.classe" in disk.columns and disk["assuntos.classe"].notna().any():
        classe_top = str(disk["assuntos.classe"].mode().iat[0])
    cols[5].metric("Classe denúncia top", classe_top if len(classe_top) <= 20 else classe_top[:18] + "…",
                   help=classe_top)

    st.info("**Narrativa gerada por IA — em breve.** Aqui entram as respostas automáticas às perguntas "
            "norteadoras (ex.: o horário de pico coincide com o QMD da FM?).")


# ---------- §2 Mapa de Calor ----------

def _polygon_records(gdf: gpd.GeoDataFrame, name_col: str) -> pd.DataFrame:
    polys = gdf[gdf.geometry.geom_type.isin(["Polygon", "MultiPolygon"])].copy()
    polys["coordinates"] = polys.geometry.apply(
        lambda g: [list(g.exterior.coords)] if g.geom_type == "Polygon"
        else [list(p.exterior.coords) for p in g.geoms]
    )
    polys["tooltip"] = polys.get(name_col, pd.Series("", index=polys.index)).astype(str)
    return pd.DataFrame(polys.drop(columns="geometry"))


def section_heatmap(ocorr: gpd.GeoDataFrame, areas: gpd.GeoDataFrame, fatores: gpd.GeoDataFrame) -> None:
    st.header("2. Mapa de Calor")
    st.caption("Concentração de roubos/furtos sobreposta às áreas da Força Municipal — identifica trechos críticos "
               "e alinhamento com a cobertura operacional.")

    show_fatores = st.checkbox("Mostrar fatores urbanos", value=False, key="cs_show_fatores")

    roubos = ocorr[ocorr["desc_delito"].fillna("").str.contains(r"Roubo|Furto", case=False, regex=True)]
    pts = roubos[roubos.geometry.geom_type == "Point"].copy()
    pts["lon"] = pts.geometry.x
    pts["lat"] = pts.geometry.y
    heat_df = pd.DataFrame(pts.drop(columns="geometry"))

    layers = []
    if not areas.empty:
        layers.append(pdk.Layer(
            "PolygonLayer", _polygon_records(areas, "nome_subar"),
            get_polygon="coordinates",
            get_fill_color=[0, 100, 200, 20], get_line_color=[0, 60, 160, 200],
            line_width_min_pixels=1, pickable=True,
        ))
    if not heat_df.empty:
        layers.append(pdk.Layer(
            "HeatmapLayer", heat_df, get_position="[lon, lat]",
            aggregation="SUM", radius_pixels=40,
        ))
    if show_fatores and not fatores.empty:
        f_pts = fatores[fatores.geometry.geom_type == "Point"].copy()
        f_pts["lon"] = f_pts.geometry.x
        f_pts["lat"] = f_pts.geometry.y
        layers.append(pdk.Layer(
            "ScatterplotLayer", pd.DataFrame(f_pts.drop(columns="geometry")),
            get_position="[lon, lat]", get_radius=30, radius_min_pixels=1, radius_max_pixels=4,
            get_fill_color=[120, 200, 80, 140],
        ))

    if not layers:
        st.info("Sem dados no período para gerar o mapa.")
        return

    st.pydeck_chart(pdk.Deck(
        layers=layers, initial_view_state=RIO_VIEW, map_style="light",
        tooltip={"text": "{tooltip}"},
    ), use_container_width=True)


# ---------- §3 Análise Temporal ----------

def _hora_band(h) -> str | None:
    if pd.isna(h):
        return None
    h = int(h)
    for lo, hi, name in HORA_BANDS:
        if lo <= h < hi:
            return name
    return None


def section_temporal(ocorr: gpd.GeoDataFrame) -> None:
    st.header("3. Análise Temporal")
    st.caption("Distribuição por dia da semana e faixa horária. Subsidia sugestão de horário de cobertura da FM.")

    if ocorr.empty:
        st.info("Sem ocorrências no período.")
        return

    df = pd.DataFrame(ocorr.drop(columns="geometry", errors="ignore"))
    df["hora"] = pd.to_numeric(df["hora"], errors="coerce")

    has_dow = "dia_semana" in df.columns and df["dia_semana"].notna().any()

    col1, col2 = st.columns(2)
    with col1:
        if has_dow and df["hora"].notna().any():
            agg = (df.dropna(subset=["dia_semana", "hora"])
                     .groupby(["dia_semana", "hora"]).size().reset_index(name="n"))
            chart = (alt.Chart(agg).mark_rect()
                     .encode(x=alt.X("hora:O", title="Hora"),
                             y=alt.Y("dia_semana:N", title="Dia"),
                             color=alt.Color("n:Q", title="Ocorrências"),
                             tooltip=["dia_semana", "hora", "n"])
                     .properties(height=260, title="Dia × Hora"))
            st.altair_chart(chart, use_container_width=True)
        elif df["hora"].notna().any():
            st.caption("`dia_semana` indisponível — exibindo apenas distribuição por hora.")
            agg = df.dropna(subset=["hora"]).groupby("hora").size().reset_index(name="n")
            chart = (alt.Chart(agg).mark_bar()
                     .encode(x="hora:O", y="n:Q", tooltip=["hora", "n"])
                     .properties(height=260, title="Ocorrências por hora"))
            st.altair_chart(chart, use_container_width=True)
        else:
            st.info("Sem dados temporais.")

    with col2:
        df["faixa"] = df["hora"].apply(_hora_band)
        top_delitos = df["desc_delito"].value_counts().head(10).index
        sub = df[df["desc_delito"].isin(top_delitos) & df["faixa"].notna()]
        if sub.empty:
            st.info("Sem dados suficientes para o gráfico por faixa.")
            return
        agg = sub.groupby(["desc_delito", "faixa"]).size().reset_index(name="n")
        chart = (alt.Chart(agg).mark_bar()
                 .encode(y=alt.Y("desc_delito:N", sort="-x", title=None),
                         x=alt.X("n:Q", title="Ocorrências"),
                         color=alt.Color("faixa:N", sort=[b[2] for b in HORA_BANDS]),
                         tooltip=["desc_delito", "faixa", "n"])
                 .properties(height=260, title="Tipo × faixa horária"))
        st.altair_chart(chart, use_container_width=True)


# ---------- §4 Dinâmica Criminal ----------

def section_denuncia(disk: gpd.GeoDataFrame, relints: pd.DataFrame | None) -> None:
    st.header("4. Dinâmica Criminal — IA Qualitativa")
    st.caption("Síntese do Disque Denúncia e RELINTs: modus operandi, perfil, rotas de fuga.")

    cols = st.columns(3)
    cols[0].metric("Denúncias no período", f"{len(disk):,}")

    with cols[1]:
        st.markdown("**Top classes**")
        if not disk.empty and "assuntos.classe" in disk.columns:
            top = disk["assuntos.classe"].value_counts().head(5)
            st.dataframe(top.rename_axis("classe").reset_index(name="n"),
                         use_container_width=True, hide_index=True)
        else:
            st.caption("—")

    with cols[2]:
        st.markdown("**Top bairros**")
        if not disk.empty and "bairro_logradouro" in disk.columns:
            top = disk["bairro_logradouro"].value_counts().head(5)
            st.dataframe(top.rename_axis("bairro").reset_index(name="n"),
                         use_container_width=True, hide_index=True)
        else:
            st.caption("—")

    if relints is not None and not relints.empty:
        with st.expander(f"RELINTs disponíveis ({len(relints)})"):
            st.dataframe(relints[["file"]], use_container_width=True, hide_index=True)

    st.info("**Síntese automática (modus operandi, perfil de suspeitos, rotas de fuga) — em breve.**")


# ---------- §5 Painel de Coincidências ----------

@st.cache_data(show_spinner=False)
def _ranking_table(ocorr_pts: pd.DataFrame, fatores_pts: pd.DataFrame, cameras_pts: pd.DataFrame,
                   areas_wkt: pd.DataFrame) -> pd.DataFrame:
    # rebuild GeoDataFrames inside the cached function to keep inputs hashable
    from shapely import wkt
    areas = gpd.GeoDataFrame(
        areas_wkt.assign(geometry=areas_wkt["wkt"].apply(wkt.loads)).drop(columns="wkt"),
        geometry="geometry", crs="EPSG:4326",
    )

    def _count(pts: pd.DataFrame, col: str) -> pd.Series:
        if pts.empty:
            return pd.Series(0, index=areas.index, name=col)
        from shapely.geometry import Point
        g = gpd.GeoDataFrame(
            pts, geometry=[Point(x, y) for x, y in zip(pts["lon"], pts["lat"])],
            crs="EPSG:4326",
        )
        joined = gpd.sjoin(g, areas[["geometry"]], how="inner", predicate="within")
        return joined.groupby("index_right").size().reindex(areas.index, fill_value=0).rename(col)

    out = pd.DataFrame({
        "nome_subar": areas["nome_subar"] if "nome_subar" in areas.columns else areas.index.astype(str),
        "crimes": _count(ocorr_pts, "crimes"),
        "fatores_urbanos": _count(fatores_pts, "fatores_urbanos"),
        "cameras": _count(cameras_pts, "cameras"),
    })
    out["crimes_por_camera"] = out["crimes"] / out["cameras"].replace(0, pd.NA)
    out["crimes_por_camera"] = out["crimes_por_camera"].fillna(out["crimes"])  # no-camera areas: raw crimes
    return out.sort_values("crimes_por_camera", ascending=False).reset_index(drop=True)


def _gdf_xy(gdf: gpd.GeoDataFrame) -> pd.DataFrame:
    pts = gdf[gdf.geometry.geom_type == "Point"]
    return pd.DataFrame({"lon": pts.geometry.x, "lat": pts.geometry.y})


def section_coincidence(ocorr: gpd.GeoDataFrame, fatores: gpd.GeoDataFrame, cameras: gpd.GeoDataFrame,
                        areas: gpd.GeoDataFrame) -> pd.DataFrame:
    st.header("5. Painel de Coincidências")
    st.caption("Cruzamento mancha criminal × fatores urbanos × cobertura de câmeras por área da FM. "
               "Critério de priorização será refinado — esta é uma aproximação inicial.")

    if areas.empty:
        st.info("Áreas FM indisponíveis.")
        return pd.DataFrame()

    areas_wkt = pd.DataFrame({
        "nome_subar": areas.get("nome_subar", pd.Series(areas.index.astype(str), index=areas.index)),
        "wkt": areas.geometry.to_wkt(),
    })
    ranking = _ranking_table(_gdf_xy(ocorr), _gdf_xy(fatores), _gdf_xy(cameras), areas_wkt)
    st.dataframe(ranking, use_container_width=True, hide_index=True)
    return ranking


# ---------- §6 Plano de Ação ----------

def section_action_plan(ranking: pd.DataFrame) -> None:
    st.header("6. Plano de Ação Gerado")
    st.info("**Sugestões geradas por IA — em revisão pelo gestor.** Pré-popula a tabela de "
            "responsabilização do CompStat.")

    if ranking.empty:
        st.caption("Aguardando dados do Painel de Coincidências.")
        return

    top = ranking.head(3)
    rows = []
    for _, r in top.iterrows():
        rows.append({
            "Área prioritária": r["nome_subar"],
            "Ação sugerida": "Reforço de patrulhamento em horário de pico",
            "Responsável": f"Comandante FM {r['nome_subar']}",
            "Justificativa": f"{int(r['crimes'])} crimes / {int(r['cameras'])} câmeras no período",
            "Status": "Em revisão",
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


# ---------- entry point ----------

def render_compstat_panel(cached_layer: Callable[[str], gpd.GeoDataFrame]) -> None:
    ocorr = cached_layer("ocorrencias")
    disk = cached_layer("disk_denuncia")
    fatores = cached_layer("fatores_urbanos")
    cameras = cached_layer("cameras")
    areas = cached_layer("areas_forca")

    try:
        import data_loader as dl
        relints = dl.load_relints()
    except Exception:
        relints = None

    p = period_filter(ocorr, disk)
    st.divider()

    section_executive(p["ocorrencias"], p["disk_denuncia"])
    st.divider()

    section_heatmap(p["ocorrencias"], areas, fatores)
    st.divider()

    section_temporal(p["ocorrencias"])
    st.divider()

    section_denuncia(p["disk_denuncia"], relints)
    st.divider()

    ranking = section_coincidence(p["ocorrencias"], fatores, cameras, areas)
    st.divider()

    section_action_plan(ranking)
