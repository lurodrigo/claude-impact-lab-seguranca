# Impact Lab — Segurança Rio

Hackathon project: consolidate Rio de Janeiro public-safety data sources and explore them in an interactive dashboard.

This project extracts insights from Disque Denuncia qualitative reports and identifies the following labels (Defined as Prompts):

```
1. **desc_delito** (tipo de crime - siga EXATAMENTE o padrão ISP):
   - "Roubo de aparelho celular" - especificamente roubo de aparelho celular (o objetivo é o celular)
   - "Roubo em coletivo (em transporte: onibus, van etc)" - roubo em transporte público
   - "Roubo a transeunte" - roubo com ameaça de violência (ou concretização de violência) contra pessoa na rua (roubos genéricos que NÃO são celular e NÃO são em transporte)
   - "Indeterminado" - se não houver informação suficiente ou não for roubo

2. **modus_operandi** (modo de operação - APENAS para crimes de roubo):
   - "Pedestre" - crime cometido com o criminoso a pé
   - "Moto" - uso de motocicleta
   - "Carro" - uso de automóvel
   - "Indeterminado" - se não especificado OU se desc_delito for "Indeterminado" (não é roubo)

3. **rotas_fuga**:
   - "Sim" se o relato menciona rotas de fuga específicas
   - "Não" se não menciona
   - "Indeterminado" se não há informação
   - Se "Sim", preencha rotas_fuga_detalhes com a descrição

4. **pontos_receptacao** (pontos de receptação/venda de produtos roubados):
   - "Sim" se o relato menciona locais de receptação
   - "Não" se não menciona
   - "Indeterminado" se não há informação
   - Se "Sim", preencha pontos_receptacao_detalhes com o local/descrição

5. **influencia_org_criminosas** (facções):
   - "Sim" se o relato menciona facções criminosas (CV, ADA, TCP, etc.)
   - "Não" se não menciona
   - "Indeterminado" se não há informação
   - Se "Sim", preencha influencia_org_criminosas_detalhes com qual facção

6. **Fatores Urbanos de Incidência Criminal** (MAIS IMPORTANTE):
   Identifique se o relato menciona algum fator urbano da tabela CompStat abaixo.
   Se SIM, preencha: fator_urbano_categoria, fator_urbano, fator_urbano_orgao_responsavel
   Se NÃO, preencha todos com "Nenhum"
```


This was previously being done "manually" with human labor, and now is completely automatized.


Generate an AI report with insights over the provided dataset. 

```
Nome da Equipe: Grupo 5
Membros: Luiz Rodrigo de Souza, Mila de Oliveira, Jean Felipe Gonçalves, Gabriel de Faro, Jether Carvalho
Tema: Segurança Pública
Abordagem: Claude utilizado para geração da interface front-end e requisição de API de modelos
Links: https://github.com/lurodrigo/claude-impact-lab-seguranca/tree/main
Video: https://drive.google.com/drive/u/0/folders/18CumCTKbrx-LsD6Tog5CYLYWffQDr64D
```

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
