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

def _build_exec_stats(ocorr: gpd.GeoDataFrame, disk: gpd.GeoDataFrame) -> dict:
    stats: dict = {}
    stats["total"] = len(ocorr)
    stats["roubos"] = int(ocorr["desc_delito"].str.startswith("Roubo", na=False).sum()) if not ocorr.empty else 0
    stats["furtos"] = int(ocorr["desc_delito"].str.startswith("Furto", na=False).sum()) if not ocorr.empty else 0

    if not ocorr.empty and "desc_delito" in ocorr.columns and ocorr["desc_delito"].notna().any():
        stats["top_delito"] = str(ocorr["desc_delito"].mode().iat[0])
    else:
        stats["top_delito"] = "—"

    if not ocorr.empty and "hora" in ocorr.columns and ocorr["hora"].notna().any():
        h = int(ocorr["hora"].dropna().mode().iat[0])
        stats["hora_pico"] = f"{h:02d}h"
    else:
        stats["hora_pico"] = "—"

    if not ocorr.empty and "aisp" in ocorr.columns and ocorr["aisp"].notna().any():
        stats["aisp_top"] = str(int(ocorr["aisp"].mode().iat[0]))
    else:
        stats["aisp_top"] = "—"

    if not ocorr.empty and "locf" in ocorr.columns:
        top_trechos = (
            ocorr["locf"].dropna().str.strip().str.title()
            .value_counts().head(3)
        )
        stats["trechos_criticos"] = "; ".join(
            f"{t} ({n} oc.)" for t, n in top_trechos.items()
        )
    else:
        stats["trechos_criticos"] = "—"

    stats["n_denuncias"] = len(disk)
    if not disk.empty and "assuntos.classe" in disk.columns and disk["assuntos.classe"].notna().any():
        stats["classe_top"] = str(disk["assuntos.classe"].mode().iat[0])
    else:
        stats["classe_top"] = "—"

    return stats


def section_executive(ocorr: gpd.GeoDataFrame, disk: gpd.GeoDataFrame) -> None:
    st.header("1. Resumo Executivo")
    st.caption("Perguntas norteadoras respondidas automaticamente para subsidiar a reunião CompStat.")

    stats = _build_exec_stats(ocorr, disk)

    cols = st.columns(6)
    cols[0].metric("Ocorrências", f"{stats['total']:,}")
    top_delito = stats["top_delito"]
    cols[1].metric("Delito + frequente", top_delito if len(top_delito) <= 20 else top_delito[:18] + "…",
                   help=top_delito)
    cols[2].metric("Hora de pico", stats["hora_pico"])
    cols[3].metric("AISP + crítica", stats["aisp_top"])
    cols[4].metric("Denúncias", f"{stats['n_denuncias']:,}")
    classe_top = stats["classe_top"]
    cols[5].metric("Classe denúncia top", classe_top if len(classe_top) <= 20 else classe_top[:18] + "…",
                   help=classe_top)

    if st.button("Gerar narrativa por IA", key="btn_exec_llm"):
        with st.spinner("Gerando análise…"):
            try:
                from llm_helper import gerar_narrativa_resumo_executivo
                narrativa = gerar_narrativa_resumo_executivo(stats)
                st.session_state["exec_narrativa"] = narrativa
            except Exception as exc:
                st.error(f"Erro ao gerar narrativa: {exc}")

    if "exec_narrativa" in st.session_state:
        st.markdown(
            f'<div style="border-left:3px solid #e63900; padding:8px 12px; '
            f'font-size:0.9em; line-height:1.6; color:inherit;">'
            f'{st.session_state["exec_narrativa"]}</div>',
            unsafe_allow_html=True,
        )


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

@st.cache_data(show_spinner="Carregando disk denúncia classificado…")
def _load_disk_classified() -> pd.DataFrame:
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))
    from disk_denuncia_loader import load_disk_denuncia_classified
    return load_disk_denuncia_classified()


def _aggregate_disk_for_area(df: pd.DataFrame, polygon) -> dict:
    from collections import Counter
    df_valid = df.dropna(subset=["latitude", "longitude"])
    if df_valid.empty:
        return {"total_denuncias": 0}

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
    df_area = df_bb[inside]
    if df_area.empty:
        return {"total_denuncias": 0}

    EXCLUDE = {"Indeterminado", "None", "nan", ""}

    def _top(col, n=5):
        if col not in df_area.columns:
            return []
        c = Counter(str(v).strip() for v in df_area[col].dropna() if str(v).strip() not in EXCLUDE)
        return [v for v, _ in c.most_common(n)]

    df_cls = df_area[df_area["desc_delito"].apply(lambda v: str(v).strip() not in EXCLUDE)] \
        if "desc_delito" in df_area.columns else df_area.iloc[0:0]

    col_classe = "assuntos.classe" if "assuntos.classe" in df_area.columns else "classe"
    return {
        "total_denuncias":     len(df_area),
        "top_classes":         _top(col_classe),
        "top_desc_delito":     _top("desc_delito"),
        "top_modus_operandi":  _top("modus_operandi"),
        "n_rotas_fuga":        int((df_cls["rotas_fuga"] == "Sim").sum()) if "rotas_fuga" in df_cls.columns else 0,
        "n_receptacao":        int((df_cls["pontos_receptacao"] == "Sim").sum()) if "pontos_receptacao" in df_cls.columns else 0,
        "n_org_criminosas":    int((df_cls["influencia_org_criminosas"] == "Sim").sum()) if "influencia_org_criminosas" in df_cls.columns else 0,
    }


def section_denuncia(disk: gpd.GeoDataFrame, areas: gpd.GeoDataFrame, relints: pd.DataFrame | None) -> None:
    st.header("4. Dinâmica Criminal — Disk Denúncia por Área de Análise")
    st.caption("Denúncias classificadas por IA, agrupadas por área da Força Municipal.")

    # Overall quick stats from regular disk data
    cols = st.columns(3)
    cols[0].metric("Denúncias no período (histórico)", f"{len(disk):,}")
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

    # Per-area breakdown from classified .numbers file
    st.subheader("Análise por área de análise (dados classificados)")

    if areas.empty:
        st.info("Áreas FM indisponíveis.")
        return

    try:
        df_classified = _load_disk_classified()
    except Exception as exc:
        st.warning(f"Não foi possível carregar disk_denuncia_classified: {exc}")
        return

    area_names = areas.get("nome_subar", pd.Series(range(len(areas)), index=areas.index)).tolist()
    sel_area = st.selectbox("Selecionar área de análise", area_names, key="disk_area_sel")

    area_row = areas[areas.get("nome_subar", pd.Series(range(len(areas)), index=areas.index)) == sel_area]
    if area_row.empty:
        return

    polygon = area_row.geometry.iloc[0]
    area_stats = _aggregate_disk_for_area(df_classified, polygon)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Denúncias na área", area_stats.get("total_denuncias", 0))
    c2.metric("Com rota de fuga", area_stats.get("n_rotas_fuga", 0))
    c3.metric("Com receptação", area_stats.get("n_receptacao", 0))
    c4.metric("Com org. criminosa", area_stats.get("n_org_criminosas", 0))

    if area_stats.get("top_classes"):
        st.caption(f"**Assuntos:** {', '.join(area_stats['top_classes'])}")
    if area_stats.get("top_desc_delito"):
        st.caption(f"**Tipos de crime:** {', '.join(area_stats['top_desc_delito'])}")
    if area_stats.get("top_modus_operandi"):
        st.caption(f"**Modus operandi:** {', '.join(area_stats['top_modus_operandi'])}")

    if st.button("Gerar análise por IA", key="btn_disk_llm"):
        with st.spinner("Gerando análise…"):
            try:
                from llm_helper import gerar_narrativa_disk_denuncia_area
                narrativa = gerar_narrativa_disk_denuncia_area(sel_area, area_stats)
                st.session_state[f"disk_narrativa_{sel_area}"] = narrativa
            except Exception as exc:
                st.error(f"Erro: {exc}")

    key = f"disk_narrativa_{sel_area}"
    if key in st.session_state:
        st.markdown(
            f'<div style="border-left:3px solid #888; padding:8px 12px; '
            f'font-size:0.9em; line-height:1.6; color:inherit;">'
            f'{st.session_state[key]}</div>',
            unsafe_allow_html=True,
        )


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

    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "1. Resumo Executivo",
        "2. Mapa de Calor",
        "3. Análise Temporal",
        "4. Dinâmica Criminal",
        "5. Coincidências",
        "6. Plano de Ação",
    ])

    ranking = pd.DataFrame()

    with tab1:
        section_executive(p["ocorrencias"], p["disk_denuncia"])
    with tab2:
        section_heatmap(p["ocorrencias"], areas, fatores)
    with tab3:
        section_temporal(p["ocorrencias"])
    with tab4:
        section_denuncia(p["disk_denuncia"], areas, relints)
    with tab5:
        ranking = section_coincidence(p["ocorrencias"], fatores, cameras, areas)
    with tab6:
        section_action_plan(ranking)
