"""
Claude API helper for generating human-readable report narratives.
Reads ANTHROPIC_API_KEY from env or .streamlit/secrets.toml.
"""
from __future__ import annotations

import os
from functools import lru_cache


def _get_api_key() -> str:
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if key:
        return key
    try:
        import streamlit as st
        return st.secrets["ANTHROPIC_API_KEY"]
    except Exception:
        pass
    # Fallback: read secrets.toml manually (for CLI usage)
    import pathlib, re
    toml = pathlib.Path(__file__).parent.parent / ".streamlit" / "secrets.toml"
    if toml.exists():
        m = re.search(r'ANTHROPIC_API_KEY\s*=\s*"([^"]+)"', toml.read_text())
        if m:
            return m.group(1)
    raise RuntimeError("ANTHROPIC_API_KEY not found in env or .streamlit/secrets.toml")


@lru_cache(maxsize=1)
def _client():
    import anthropic
    return anthropic.Anthropic(api_key=_get_api_key())


_SYSTEM_PROMPT = (
    "Você é um analista especializado em segurança pública municipal do Rio de Janeiro. "
    "Gere textos objetivos, factuais e em português brasileiro. "
    "Use linguagem técnica mas acessível para gestores públicos. "
    "Seja conciso: sem introduções desnecessárias, sem repetir dados já óbvios nos números. "
    "Não use markdown, bullet points ou formatação especial — apenas parágrafos corridos."
)


def _call(prompt: str, max_tokens: int = 400) -> str:
    resp = _client().messages.create(
        model="claude-sonnet-4-6",
        max_tokens=max_tokens,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.content[0].text.strip()


# ─────────────────────────────────────────────────────────────────────────────
# Resumo Executivo
# ─────────────────────────────────────────────────────────────────────────────

def gerar_resumo_executivo(
    nome_area: str,
    indicadores: dict,
    identificacao: dict,
    fatores: list[dict],
    coincidencias: list[dict],
    disk_denuncia_resumo: str = "",
) -> str:
    """
    Generates a 2-3 paragraph executive summary for the area.
    Replaces the previous template-string approach.
    """
    top3 = identificacao.get("trechos_criticos", [])[:3]
    trechos_txt = "; ".join(f"{t['logradouro']} ({t['ocorrencias']} oc.)" for t in top3) or "não identificados"

    ranking_pos   = indicadores.get("ranking_pos")
    ranking_total = indicadores.get("ranking_total_areas", 8)
    ranking_pct   = indicadores.get("ranking_pct")
    variacao      = indicadores.get("variacao_pct")
    variacao_txt  = f"{variacao:+.1f}%" if variacao is not None else "sem comparativo"

    bingos = sum(1 for c in coincidencias if c.get("coincidencia"))

    fatores_top = [f["fator"] for f in fatores[:4]]
    fatores_txt = "; ".join(fatores_top) if fatores_top else "nenhum registrado"

    disk_section = f"\n\nDados do Disque Denúncia para a área: {disk_denuncia_resumo}" if disk_denuncia_resumo else ""

    prompt = (
        f"Área de análise: {nome_area}.\n"
        f"Período: {indicadores.get('periodo', '—')}.\n"
        f"Total de ocorrências: {indicadores.get('total', 0)} "
        f"({indicadores.get('roubos', 0)} roubos, {indicadores.get('furtos', 0)} furtos). "
        f"Variação vs período anterior: {variacao_txt}.\n"
        f"Ranking: {ranking_pos}º de {ranking_total} áreas FM ({ranking_pct}% das ocorrências da cidade).\n"
        f"Trechos críticos: {trechos_txt}.\n"
        f"Grupos criminosos: {identificacao.get('grupos_criminosos', '—')}.\n"
        f"Fatores urbanos identificados: {fatores_txt}.\n"
        f"Trechos com coincidência crime + fator urbano: {bingos} de {len(coincidencias)}."
        f"{disk_section}\n\n"
        "Escreva um resumo executivo para gestores em 2-3 parágrafos curtos, "
        "destacando o nível de incidência criminal, os principais trechos críticos, "
        "e os fatores ambientais de risco que demandam ação intersetorial."
    )
    return _call(prompt, max_tokens=800)


# ─────────────────────────────────────────────────────────────────────────────
# Seção 4 — Disk Denúncia por área
# ─────────────────────────────────────────────────────────────────────────────

def gerar_resumo_disk_denuncia(nome_area: str, stats: dict) -> str:
    """
    Generates a narrative summary for the disk_denuncia classified data
    filtered to one FM area polygon.

    stats keys (all optional / may be zero):
        total_denuncias, top_classes, top_desc_delito, top_modus_operandi,
        n_rotas_fuga, rotas_fuga_detalhes, n_receptacao, receptacao_detalhes,
        n_org_criminosas, org_criminosas_detalhes
    """
    total = stats.get("total_denuncias", 0)
    if total == 0:
        return "Nenhuma denúncia registrada para esta área no período analisado."

    def _fmt(lst: list, n: int = 5) -> str:
        return "; ".join(lst[:n]) if lst else "não identificado"

    prompt = (
        f"Área de análise: {nome_area}.\n"
        f"Total de denúncias Disque Denúncia na área: {total}.\n"
        f"Principais assuntos/classes: {_fmt(stats.get('top_classes', []))}.\n"
        f"Tipos de crime mais denunciados: {_fmt(stats.get('top_desc_delito', []))}.\n"
        f"Modus operandi mais frequente: {_fmt(stats.get('top_modus_operandi', []))}.\n"
        f"Denúncias com informação de rota de fuga: {stats.get('n_rotas_fuga', 0)} "
        f"({_fmt(stats.get('rotas_fuga_detalhes', []))}).\n"
        f"Denúncias com pontos de receptação: {stats.get('n_receptacao', 0)} "
        f"({_fmt(stats.get('receptacao_detalhes', []))}).\n"
        f"Denúncias com influência de organização criminosa: {stats.get('n_org_criminosas', 0)} "
        f"({_fmt(stats.get('org_criminosas_detalhes', []))}).\n\n"
        "Com base nesses dados, escreva um parágrafo analítico sobre a dinâmica criminal "
        "desta área segundo as denúncias recebidas, destacando padrões de modus operandi, "
        "logística criminal (rotas de fuga, receptação) e eventual influência de organizações criminosas. "
        "Se os dados forem escassos, indique isso de forma direta."
    )
    return _call(prompt, max_tokens=350)
