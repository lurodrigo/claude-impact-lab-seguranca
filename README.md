# Impact Lab — Segurança Rio

Hackathon project: consolidate Rio de Janeiro public-safety data sources and explore them in an interactive dashboard.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run the dashboard

```bash
streamlit run app.py
```

## Layout

- `dados/` — raw data (CSV / XLSX / shapefile / DOCX reports). See `dados/Dicionário de dados.xlsx`.
- `sh_area_forca/` — shapefile of municipal force areas (polygons, WGS84).
- `relints/` — intelligence reports (DOCX).
- `data_loader.py` — normalizes every source into `GeoDataFrame`s in EPSG:4326 and exposes a DuckDB layer for SQL across them.
- `app.py` — Streamlit dashboard.

## Data sources (current)

| Source | Type | Geometry |
|---|---|---|
| `cameras_areas_fm.csv` | camera points by force area | POINT |
| `df_ocorrencias_tratado` | crime occurrences (year, hour, type) | POINT |
| `disk_denuncia.csv` | anonymous tips (latin-1, comma decimals) | POINT |
| `fatores_urbanos.csv` | urban risk factors | POINT |
| `dominio_territorial` | organized-crime territorial domain | POLYGON |
| `sh_area_forca/` | municipal force areas | POLYGON |
| `relints/*.docx` | intelligence reports | text |
