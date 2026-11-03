"""Constantes do projeto (ver spec.md, seções 2, 5 e 7)."""
from pathlib import Path

LAT = -28.26
LON = -52.41
ALT = 687

DATA_INICIO = "2010-01-01"
DATA_FIM = "2025-06-30"

# Parâmetros de referência do FAO-56 (spec.md, seção 5): a equipe deve conferi-los.
CULTURAS = {
    "milho": {"kc_ini": 0.30, "kc_mid": 1.20, "kc_end": 0.60, "estagios": (30, 40, 50, 30), "zr": 1.0, "p": 0.55},
    "soja": {"kc_ini": 0.40, "kc_mid": 1.15, "kc_end": 0.50, "estagios": (20, 30, 60, 25), "zr": 1.0, "p": 0.50},
    "feijão": {"kc_ini": 0.40, "kc_mid": 1.15, "kc_end": 0.35, "estagios": (20, 30, 40, 20), "zr": 0.7, "p": 0.45},
}

SOLOS = {
    "arenoso": {"fc": 0.12, "wp": 0.045},
    "médio": {"fc": 0.25, "wp": 0.12},
    "argiloso": {"fc": 0.36, "wp": 0.22},
}

ALPHA = 0.5
SEED = 42
CHUVA_MIN = 5.0
MAX_DIAS = 60

DATAS_SEMEADURA = [(10, 1), (10, 15), (11, 1), (11, 15), (12, 1)]
ANOS_SEMEADURA = range(2010, 2025)
ANOS_TREINO = range(2010, 2020)
ANOS_VALIDACAO = (2020, 2021)
ANOS_TESTE = (2022, 2023, 2024)

RAIZ = Path(__file__).parent
DATA_DIR = RAIZ / "data"
MODELS_DIR = RAIZ / "models"
REPORTS_DIR = RAIZ / "reports"

NOMES_CLASSES = {
    0: "Sem necessidade de irrigação",
    1: "Atenção: irrigação em breve",
    2: "Irrigação recomendada",
}

AVISO = (
    "Recomendação de suporte à decisão, baseada em dados climáticos e em rótulos "
    "simulados pelo método FAO-56. Não substitui avaliação técnica nem garante "
    "economia de água."
)
