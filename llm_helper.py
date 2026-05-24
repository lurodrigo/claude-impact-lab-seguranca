"""
Shared Claude API helper for the Streamlit app.
Reads ANTHROPIC_API_KEY from env or .streamlit/secrets.toml.
"""
from __future__ import annotations

import os
import re
import pathlib
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
    toml = pathlib.Path(__file__).parent / ".streamlit" / "secrets.toml"
    if toml.exists():
        m = re.search(r'ANTHROPIC_API_KEY\s*=\s*"([^"]+)"', toml.read_text())
        if m:
            return m.group(1)
    raise RuntimeError("ANTHROPIC_API_KEY not found")


@lru_cache(maxsize=1)
def _client():
    import anthropic
    return anthropic.Anthropic(api_key=_get_api_key())


_SYSTEM = (
    "Você é um analista especializado em segurança pública municipal do Rio de Janeiro. "
    "Gere textos objetivos, factuais e em português brasileiro. "
    "Use linguagem técnica mas acessível para gestores públicos. "
    "Seja conciso. Não use markdown, bullet points ou formatação especial — apenas parágrafos corridos."
)


def call_llm(prompt: str, max_tokens: int = 600) -> str:
    resp = _client().messages.create(
        model="claude-sonnet-4-6",
        max_tokens=max_tokens,
        system=_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.content[0].text.strip()


def gerar_narrativa_resumo_executivo(stats: dict) -> str:
    prompt = (
        f"Período analisado: {stats.get('periodo', '—')}.\n"
        f"Total de ocorrências: {stats.get('total', 0)} "
        f"({stats.get('roubos', 0)} roubos, {stats.get('furtos', 0)} furtos).\n"
        f"Variação vs período anterior: {stats.get('variacao', 'sem comparativo')}.\n"
        f"Hora de pico: {stats.get('hora_pico', '—')}.\n"
        f"AISP mais crítica: {stats.get('aisp_top', '—')}.\n"
        f"Top tipo de crime: {stats.get('top_delito', '—')}.\n"
        f"Total de denúncias Disque Denúncia: {stats.get('n_denuncias', 0)}.\n"
        f"Classe de denúncia mais frequente: {stats.get('classe_top', '—')}.\n"
        f"Trechos mais críticos: {stats.get('trechos_criticos', '—')}.\n\n"
        "Escreva um resumo executivo em 2-3 parágrafos para gestores de segurança pública, "
        "sintetizando o quadro criminal do período, os principais focos e padrões temporais, "
        "e recomendando prioridades de ação com base nos dados."
    )
    return call_llm(prompt, max_tokens=700)


def gerar_narrativa_disk_denuncia_area(nome_area: str, stats: dict) -> str:
    total = stats.get("total_denuncias", 0)
    if total == 0:
        return "Nenhuma denúncia registrada para esta área no período."

    def _fmt(lst, n=4):
        return "; ".join(lst[:n]) if lst else "não identificado"

    prompt = (
        f"Área: {nome_area}. Total de denúncias: {total}.\n"
        f"Assuntos principais: {_fmt(stats.get('top_classes', []))}.\n"
        f"Tipos de crime: {_fmt(stats.get('top_desc_delito', []))}.\n"
        f"Modus operandi: {_fmt(stats.get('top_modus_operandi', []))}.\n"
        f"Denúncias com rota de fuga: {stats.get('n_rotas_fuga', 0)}.\n"
        f"Denúncias com receptação: {stats.get('n_receptacao', 0)}.\n"
        f"Denúncias com org. criminosa: {stats.get('n_org_criminosas', 0)}.\n\n"
        "Escreva um parágrafo analítico sobre a dinâmica criminal desta área segundo as denúncias, "
        "destacando padrões de modus operandi, logística criminal e influência de organizações criminosas. "
        "Se os dados forem escassos, diga isso diretamente."
    )
    return call_llm(prompt, max_tokens=300)
