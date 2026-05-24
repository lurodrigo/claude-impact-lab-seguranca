"""
Seção 4 — Fatores de Incidência Criminal
Aggregates urban factors and camera data for the selected area.
"""
from __future__ import annotations

import pandas as pd


def calcular_fatores(df_fatores: pd.DataFrame) -> list[dict]:
    """
    Groups urban factors by type, collects descriptions and the responsible agency.
    Returns a list of factor groups ordered by frequency (most prevalent first).
    """
    if df_fatores.empty:
        return []

    results = []
    grouped = df_fatores.groupby("tipo_ocorrencia_descricao", dropna=True)

    for tipo, group in grouped:
        # Responsible agency — take the most common non-null value
        orgao = (
            group["orgao_responsavel"]
            .dropna()
            .mode()
        )
        orgao_str = orgao.iloc[0] if not orgao.empty else "—"

        # Collect unique descriptive texts from `observacao` and street references
        ruas = (
            group["logradouro"]
            .dropna()
            .str.strip()
            .str.title()
            .unique()
            .tolist()
        )
        # Build a concise description from the logradouros identified
        if ruas:
            ruas_str = "; ".join(ruas[:8])  # cap at 8 to avoid wall of text
            descricao = f"Identificado em: {ruas_str}."
        else:
            descricao = "Ocorrências registradas na área."

        # Also pull any free-text observacao that isn't the standard HTML template
        obs_texts = (
            group["observacao"]
            .dropna()
            .str.strip()
            .unique()
            .tolist()
        )
        obs_clean = [o for o in obs_texts if len(o) < 300 and "<img" not in o]
        if obs_clean:
            descricao = obs_clean[0]

        results.append({
            "fator":       str(tipo).strip(),
            "descricao":   descricao,
            "orgao":       str(orgao_str).strip(),
            "quantidade":  len(group),
        })

    results.sort(key=lambda x: -x["quantidade"])
    return results


def calcular_psr(df_cpsr: pd.DataFrame) -> dict:
    """
    Summarises People in Street Situation (PSR) data for the area.
    Uses the CPSR census dataset filtered by polygon.
    """
    if df_cpsr.empty:
        return {"total": 0, "anos": [], "bairros": []}

    total = len(df_cpsr)
    anos  = sorted(df_cpsr["Ano"].dropna().astype(int).unique().tolist()) if "Ano" in df_cpsr.columns else []

    bairros = []
    if "Nome do Bairro" in df_cpsr.columns:
        bairros = (
            df_cpsr["Nome do Bairro"]
            .dropna()
            .value_counts()
            .head(5)
            .index.tolist()
        )

    return {
        "total":   total,
        "anos":    anos,
        "bairros": bairros,
    }


def calcular_cameras(df_cameras: pd.DataFrame) -> dict:
    """Returns camera count summary for the area."""
    return {
        "total":    len(df_cameras),
        "descricao": f"Total de {len(df_cameras)} câmeras de vigilância identificadas na área.",
    }


_ACAO_TEMPLATE: dict[str, tuple[str, str, str]] = {
    "Vegetação obstruindo a visibilidade do passeio":
        ("SECONSERVA", "Poda de vegetação nos logradouros indicados para restaurar visibilidade do passeio", "15 dias"),
    "Lixo/entulho forçando pedestres à pista":
        ("COMLURB", "Remoção de lixo/entulho e notificação do gerador de resíduos", "5 dias"),
    "Área mal iluminada com circulação de pedestres":
        ("Rio Luz", "Substituição ou reparo de luminárias nos pontos críticos identificados", "10 dias"),
    "Área mal iluminada com parada de veículos":
        ("Rio Luz", "Substituição ou reparo de luminárias — priorizar pontos de parada", "10 dias"),
    "Mobiliário urbano desviando pedestres para a pista":
        ("SECONSERVA", "Relocação de mobiliário urbano ou alargamento de calçada", "30 dias"),
    "Calçada estreita forçando pedestres à pista":
        ("SECONSERVA", "Intervenção de qualificação de calçada — priorizar trechos críticos", "30 dias"),
    "Mobiliário/estrutura servindo de esconderijo":
        ("SEOP", "Remoção ou relocação de estrutura identificada como facilitadora de crime", "15 dias"),
    "Comércio irregular obstruindo a visibilidade do passeio":
        ("SEOP", "Fiscalização e notificação do comércio irregular; remoção se reincidente", "10 dias"),
    "Estacionamento irregular forçando pedestres à pista":
        ("CET-Rio", "Operação de fiscalização de estacionamento irregular no trecho", "Imediato"),
    "Veículos de grande porte obstruindo a visibilidade":
        ("SMTR", "Restrição de circulação de veículos pesados em horário de pico criminal", "15 dias"),
    "Pessoas em situação de rua":
        ("SMAS", "Acionamento de equipe de abordagem social da SMAS para o trecho", "5 dias"),
    "Cena de uso de drogas":
        ("GM-Rio / SEOP", "Operação ostensiva de remoção de cena aberta de uso de drogas", "Imediato"),
}


def calcular_plano_de_acao(fatores: list[dict]) -> list[dict]:
    """
    Pre-fills action plan rows derived from identified urban factors.
    Each factor type maps to a standard agency + recommended action + deadline.
    Returns list of dicts: {acao, responsavel, prazo, fator_origem}.
    """
    rows = []
    seen: set[str] = set()
    for f in fatores:
        tipo = f.get("fator", "")
        if tipo in _ACAO_TEMPLATE and tipo not in seen:
            resp, acao_txt, prazo = _ACAO_TEMPLATE[tipo]
            rows.append({
                "acao":         acao_txt,
                "responsavel":  resp,
                "prazo":        prazo,
                "fator_origem": tipo,
            })
            seen.add(tipo)
    return rows
