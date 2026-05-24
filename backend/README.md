# Backend — CompStat Rio: Gerador de Relatórios

Motor determinístico de geração de relatório analítico de área para o CompStat Municipal.
Recebe um ID de polígono FM, calcula todos os indicadores, e exporta HTML ou PDF pronto.

**Sem LLM no fluxo.** As seções que dependem de LLM (Seção 2 — Dinâmica Criminal, Resumo Executivo Q2/Q3) aparecem como placeholder no relatório final.

---

## Instalação

```bash
pip install -r requirements.txt

# Instalar o Chromium para geração de PDF (uma vez só):
playwright install chromium
```

**Python**: 3.11 ou 3.12

---

## Uso via CLI

```bash
# Listar áreas disponíveis (com fid)
python main.py --list-areas

# Gerar relatório PDF completo para a área fid=12 (Rio Sul / Lauro Müller)
python main.py --fid 12 --ano-inicio 2023 --ano-fim 2024 --mes-ref "Maio 2026"

# Apenas HTML (mais rápido, sem PDF)
python main.py --fid 12 --html-only

# Sem mapas (mais rápido ainda, para validação de dados)
python main.py --fid 12 --no-maps

# Dump do contexto como JSON (debug)
python main.py --fid 12 --json-ctx --no-maps
```

---

## Uso como biblioteca (para Streamlit)

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))

from report_generator import gerar_contexto_relatorio, listar_areas
from pdf_exporter import renderizar_html, exportar_pdf
```

### 1. Popular o dropdown de áreas

```python
areas = listar_areas()
# Retorna: [{"fid": 10, "nome": "Rodoviária / Terminal Gentileza"}, ...]
```

### 2. Gerar o contexto completo

```python
ctx = gerar_contexto_relatorio(
    shapefile_fid  = 12,          # int: fid da área selecionada
    ano_inicio     = 2023,        # int: primeiro ano da janela criminal
    ano_fim        = 2024,        # int: último ano da janela criminal
    mes_referencia = "Maio 2026", # str: exibido no cabeçalho do relatório
    gerar_mapas    = True,        # bool: False = sem imagens (10x mais rápido)
)
```

**Tempos esperados (fid=12, com mapas):**
- Primeira execução: ~25 s (carrega CSVs + XLSX → gera cache parquet)
- Execuções seguintes: ~12 s (cache parquet)
- `gerar_mapas=False`: ~12 s / ~2 s respectivamente

### 3. Exportar

```python
# HTML como string (para st.download_button)
html_str = renderizar_html(ctx)

# PDF para arquivo
exportar_pdf(ctx, "/tmp/relatorio.pdf")

# HTML para arquivo
from pdf_exporter import exportar_html
exportar_html(ctx, "/tmp/relatorio.html")
```

---

## Schema do contexto (`ctx`)

O dict retornado por `gerar_contexto_relatorio()` tem as seguintes chaves:

### `meta` — cabeçalho do relatório
```python
{
    "nome_area":        str,   # "Rua Lauro Müller – Av. General Severiano – Av. Venceslau Brás"
    "periodo_criminal": str,   # "2023–2024"
    "mes_referencia":   str,   # "Maio 2026"
    "shapefile_fid":    int,   # 12
}
```

### `identificacao` — dados da área (Seção 1)
```python
{
    "nome_area":          str,          # igual a meta.nome_area
    "aisp":               str,          # "2"
    "dp":                 str,          # "10ª / 12ª"
    "bpm":                str,          # "2º / 19º"
    "bairros":            str,          # "Botafogo / Urca"
    "grupos_criminosos":  str,          # "CV / TCP" ou "Comunidades próximas sob domínio do CV"
    "n_trechos_criticos": int,
    "trechos_criticos":   list[dict],   # [{logradouro, ocorrencias}, ...] top 5
    "dominios_lista":     list[dict],   # [{nome, orcrim, tipo:"intersecta"|"proximidade"}, ...]
}
```

### `indicadores` — KPIs do período
```python
{
    "periodo":              str,          # "2023–2024"
    "total":                int,          # total de ocorrências no período
    "roubos":               int,
    "furtos":               int,
    "variacao_pct":         float|None,   # % vs período anterior equivalente (None se sem dados)
    "total_anterior":       int,
    "ranking_pos":          int|None,     # posição entre as 8 áreas FM
    "ranking_pct":          float|None,   # % do total da cidade
    "ranking_total_areas":  int,
    "serie_mensal":         list[dict],   # [{ano, mes, total}, ...] para gráfico
}
```

### `tipos` — distribuição por tipo de crime
```python
list[dict]  # ordenado por quantidade desc
# cada item:
{
    "ranking":      int,
    "tipo":         str,    # "Roubo a transeunte", "Roubo de aparelho celular", "Roubo em coletivo"
    "quantidade":   int,
    "ultima_data":  str,    # "2024-12-15" ou "—"
    "variacao_pct": float|None,
}
```

### `temporal` — análise hora × dia da semana
```python
{
    "matrix":      list[list[dict]],  # [hora][dia] com {hora, dia, count, intensity}
    "hours":       list[int],         # [0..23]
    "days":        list[int],         # dias presentes (1=Dom .. 7=Sáb)
    "day_labels":  list[str],         # ["Dom","Seg",...]
    "hora_pico":   int,               # hora com mais crimes
    "dia_pico":    int,               # dia com mais crimes
    "h_inicio":    int,               # início da janela crítica
    "h_fim":       int,               # fim da janela crítica
    "max_val":     int,               # valor máximo na matrix (para normalizar)
    "resumo_texto": str,              # "Todos os dias entre 12h e 21h, com pico às 19h. Maior concentração: Sex."
}
```

### `fatores` — fatores urbanos identificados (Seção 4)
```python
list[dict]  # ordenado por quantidade desc
# cada item:
{
    "fator":      str,   # tipo de fator, ex: "Área mal iluminada com circulação de pedestres"
    "descricao":  str,   # texto livre do campo observacao
    "orgao":      str,   # "Rio Luz", "SECONSERVA", etc.
    "quantidade": int,
}
```

### `psr` — Pessoas em Situação de Rua (CPSR)
```python
{
    "total":   int,        # total de registros na área
    "anos":    list[int],  # [2020, 2022, 2024]
    "bairros": list[str],  # top 5 bairros
}
```

### `cameras`
```python
{
    "total":    int,
    "descricao": str,
}
```

### `dominios` — domínio territorial (orcrim)
```python
list[dict]
# cada item:
{
    "nome":   str,   # nome da comunidade/território
    "orcrim": str,   # "CV", "TCP", "ADA", etc.
    "tipo":   str,   # "intersecta" (sobreposição direta) | "proximidade" (buffer 1.5 km)
}
```

### `coincidencias` — Painel de Coincidências (Seção 5, novo)
```python
list[dict]  # um item por trecho crítico
# cada item:
{
    "trecho":      str,        # nome do logradouro
    "ocorrencias": int,
    "fatores":     list[str],  # fatores urbanos encontrados no raio de ~70 m
    "coincidencia": bool,      # True = BINGO (crime + fator urbano sobrepostos)
}
```

### `resumo_exec` — Resumo Executivo (novo)
```python
{
    "q1_texto":    str,        # pergunta 1
    "q1_resposta": str,        # trechos mais críticos — preenchido automaticamente
    "q2_texto":    str,
    "q2_resposta": None,       # PLACEHOLDER: requer dado operacional FM
    "q3_texto":    str,
    "q3_resposta": None,       # PLACEHOLDER: requer log de ações anteriores
    "q4_texto":    str,
    "q4_resposta": str,        # fatores com órgão responsável — preenchido automaticamente
    "n_bingos":         int,   # trechos com coincidência
    "n_total_trechos":  int,
    "ranking_resumo":   str,   # "6º lugar entre 8 áreas FM (4.8% das ocorrências)"
}
```

### `plano` — Plano de Ação pré-preenchido (novo)
```python
list[dict]  # uma linha por fator com mapeamento conhecido
# cada item:
{
    "fator_origem": str,  # tipo de fator de origem
    "acao":         str,  # ação recomendada padrão
    "responsavel":  str,  # órgão responsável
    "prazo":        str,  # "Imediato", "5 dias", "10 dias", "15 dias", "30 dias"
}
```

### Imagens base64 (PNG, ~150 dpi)
```python
"img_mapa_hotspot"  # str: mapa com crimes, câmeras e fatores urbanos sobrepostos
"img_heatmap"       # str: heatmap 24h × 7 dias
"img_serie_mensal"  # str: gráfico de barras mensal
# Todas retornam "" quando gerar_mapas=False
```

---

## Estrutura de arquivos

```
backend/
├── config.py           # PATHS, AISP→DP/BPM lookup, constantes
├── data_loader.py      # Carregamento com cache LRU (CSV, XLSX→parquet)
├── spatial.py          # Point-in-polygon, filtros por dataset, filter_dominio
├── map_generator.py    # matplotlib: hotspot map, heatmap, série mensal → base64
├── pdf_exporter.py     # Jinja2 → HTML; Playwright → PDF
├── report_generator.py # Orquestrador principal: gerar_contexto_relatorio()
├── main.py             # CLI
├── requirements.txt
├── sections/
│   ├── secao1.py       # identificacao, indicadores, tipos, heatmap_temporal
│   ├── secao4.py       # fatores, psr, cameras, plano_de_acao
│   └── secao5.py       # coincidencias, resumo_executivo
└── templates/
    └── relatorio.html  # Template Jinja2 do relatório (8 páginas A4)
```

---

## Status de cada seção

| Seção | Status | Notas |
|-------|--------|-------|
| Resumo Executivo — Q1 (trechos críticos) | Automático | derivado de ocorrências |
| Resumo Executivo — Q4 (fatores em tratamento) | Automático | derivado de fatores urbanos |
| Resumo Executivo — Q2/Q3 | **Placeholder** | requer dado operacional FM |
| Mapa de hotspot (crimes + câmeras + fatores) | Automático | matplotlib + contextily |
| Heatmap hora × dia + série mensal | Automático | |
| Trechos críticos top-5 | Automático | |
| Distribuição por tipo de crime | Automático | |
| Ranking entre áreas FM | Automático | itera os 8 polígonos |
| Painel de Coincidências | Automático | crime × fator ≈ 70 m |
| Seção 2 — Dinâmica Criminal | **Placeholder** | requer LLM sobre disk_denuncia + RELINTs |
| Seção 3 — Efetivo FM | **Placeholder** | dado operacional FM indisponível |
| Seção 4 — Fatores Urbanos | Automático | |
| Seção 4 — PSR (CPSR) | Automático | |
| Seção 4 — Câmeras | Automático | |
| Plano de Ação (pré-preenchido) | Automático | fator → órgão → ação padrão |

---

## Notas para o Streamlit dev

- **`listar_areas()`** retorna os 8 polígonos do shapefile — use como opções do `st.selectbox`.
- **Cache automático**: `data_loader.py` usa `@lru_cache` — os dados ficam em memória enquanto o processo está vivo. Se o Streamlit recarregar o processo, o CPSR vai demorar ~30s na primeira vez (depois gera `.parquet` e fica < 1s).
- **`gerar_mapas=False`** é útil para mostrar os dados em tela antes de gerar o PDF — o usuário não precisa esperar o matplotlib.
- **As imagens** (`img_mapa_hotspot`, `img_heatmap`, `img_serie_mensal`) são strings base64 prontas para `<img src="data:image/png;base64,...">` ou `st.image(base64.b64decode(ctx["img_mapa_hotspot"]))`.
- **O PDF** requer Playwright com Chromium instalado. Em ambiente cloud (Streamlit Cloud, Heroku), verifique se o Chromium está disponível — pode ser necessário `playwright install chromium` no build.
- **Nomes de arquivo de dados**: os paths estão em `config.py`. Se a estrutura de pastas mudar, edite só o dict `PATHS` lá.
