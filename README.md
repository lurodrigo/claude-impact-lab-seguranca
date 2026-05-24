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

- `data/<source>/*.csv` — what the loader reads. Each weekly upload adds another file to the corresponding folder; the loader concatenates and dedupes by id. Static sources (cameras, dominio_territorial, areas_forca shapefile) live here too but only ever contain one file.
- `next_inputs/<source>/week_N.csv` — simulated weekly drops, used to test the upload flow without waiting for real data.
- `dados/` — original snapshot, untouched. Source of truth for the bootstrap script. See `dados/Dicionário de dados.xlsx`.
- `relints/` — intelligence reports (DOCX).
- `scripts/bootstrap_data.py` — one-shot: rebuilds `data/` + `next_inputs/` from `dados/`.
- `data_loader.py` — normalizes every source into `GeoDataFrame`s in EPSG:4326 and exposes a DuckDB layer for SQL across them.
- `app.py` — Streamlit dashboard. Sidebar expander **"Adicionar dados da semana"** uploads new CSVs into `data/<source>/upload_<timestamp>.csv`.

## Adding weekly data

Either drop the CSV into the matching `data/<source>/` folder, or upload it through the sidebar in the dashboard. The three weekly sources are `ocorrencias`, `disk_denuncia`, and `fatores_urbanos`; uploads are validated (required columns, encoding) before being written.

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
