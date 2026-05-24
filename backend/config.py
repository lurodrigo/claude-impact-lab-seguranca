"""
Static configuration: paths, AISP→DP/BPM lookup, and area name mapping.

AISP (Área Integrada de Segurança Pública) is a Rio de Janeiro administrative
zone grouping delegacias (DP) and military police battalions (BPM). The mapping
is fixed by state decree and does not change with the data.
"""
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DADOS_DIR = os.path.join(BASE_DIR, "dados")
SHP_DIR = os.path.join(BASE_DIR, "sh_area_forca")

# ── Data file paths ──────────────────────────────────────────────────────────
PATHS = {
    "ocorrencias":    os.path.join(DADOS_DIR, "df_ocorrencias_tratado - Extração 1 .csv"),
    "fatores":        os.path.join(DADOS_DIR, "fatores_urbanos.csv"),
    "cameras":        os.path.join(DADOS_DIR, "cameras_areas_fm.csv"),
    "dominio":        os.path.join(DADOS_DIR, "outros dados", "dominio_territorial - Extração 1.csv"),
    "cpsr":           os.path.join(DADOS_DIR, "outros dados", "CPSR_2020_2022_2024.xlsx"),
    "shapefile":      os.path.join(SHP_DIR, "areas_forca_municipal"),
}

# ── Crime period defaults ─────────────────────────────────────────────────────
DEFAULT_ANO_INICIO = 2023
DEFAULT_ANO_FIM    = 2024

# ── AISP → DP + BPM mapping (Rio de Janeiro, public administrative data) ──────
# Source: Decreto estadual SESEG/RJ — estrutura das AISPs
AISP_INFO: dict[int, dict] = {
    1:  {"dp": ["1ª", "2ª"],           "bpm": ["1º"]},
    2:  {"dp": ["10ª", "12ª"],         "bpm": ["2º", "19º"]},
    3:  {"dp": ["4ª", "6ª"],           "bpm": ["4º"]},
    4:  {"dp": ["5ª", "17ª"],          "bpm": ["5º"]},
    5:  {"dp": ["7ª"],                 "bpm": ["6º"]},
    6:  {"dp": ["14ª", "15ª"],         "bpm": ["9º"]},
    7:  {"dp": ["16ª", "17ª"],         "bpm": ["14º"]},
    8:  {"dp": ["18ª"],                "bpm": ["11º"]},
    9:  {"dp": ["19ª", "39ª"],         "bpm": ["16º"]},
    10: {"dp": ["20ª", "21ª"],         "bpm": ["17º"]},
    12: {"dp": ["13ª", "34ª"],         "bpm": ["3º"]},
    14: {"dp": ["11ª", "23ª"],         "bpm": ["23º"]},
    15: {"dp": ["22ª", "24ª"],         "bpm": ["18º"]},
    16: {"dp": ["26ª", "27ª"],         "bpm": ["21º"]},
    17: {"dp": ["28ª", "29ª"],         "bpm": ["12º"]},
    18: {"dp": ["30ª"],                "bpm": ["31º"]},
    19: {"dp": ["31ª", "32ª"],         "bpm": ["22º"]},
    20: {"dp": ["33ª"],                "bpm": ["24º"]},
    21: {"dp": ["35ª", "36ª"],         "bpm": ["27º"]},
    22: {"dp": ["37ª"],                "bpm": ["25º"]},
    23: {"dp": ["38ª"],                "bpm": ["26º"]},
    24: {"dp": ["40ª", "41ª"],         "bpm": ["28º"]},
    25: {"dp": ["42ª", "43ª"],         "bpm": ["29º"]},
    26: {"dp": ["44ª", "45ª"],         "bpm": ["30º"]},
    27: {"dp": ["46ª"],                "bpm": ["32º"]},
    28: {"dp": ["47ª", "48ª"],         "bpm": ["33º"]},
    33: {"dp": ["51ª"],                "bpm": ["40º"]},
    34: {"dp": ["50ª"],                "bpm": ["39º"]},
    40: {"dp": ["35ª"],                "bpm": ["40º"]},
    41: {"dp": ["52ª"],                "bpm": ["41º"]},
    43: {"dp": ["54ª"],                "bpm": ["43º"]},
}

def get_aisp_info(aisp: int) -> dict:
    info = AISP_INFO.get(aisp, {})
    return {
        "dp":  " / ".join(info.get("dp", ["—"])),
        "bpm": " / ".join(info.get("bpm", ["—"])),
    }

# ── Day-of-week labels (Portuguese, 1=Sunday per the data) ───────────────────
DIAS_SEMANA = {
    "1": "Dom", "2": "Seg", "3": "Ter",
    "4": "Qua", "5": "Qui", "6": "Sex", "7": "Sáb",
}

# ── Crime type labels (canonical) ─────────────────────────────────────────────
CRIME_TYPES = [
    "Roubo a transeunte",
    "Roubo de aparelho celular",
    "Roubo em coletivo",
]
