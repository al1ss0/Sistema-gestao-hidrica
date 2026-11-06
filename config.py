"""Constantes do projeto (ver spec.md, seções 2, 5 e 7)."""
from pathlib import Path

LAT = -28.26
LON = -52.41
ALT = 687

LOCAL_NOME = "Passo Fundo – RS"

# Início da série histórica usada no treino. Não há data final fixa: o clima vai até o
# último dia completo disponível na fonte (ver hidrica/clima.py).
DATA_INICIO = "2010-01-01"

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

# Domínio em que o modelo foi treinado (ver hidrica/localidade.py, motivos_extrapolacao):
# um único ponto de clima (Passo Fundo) e análises de outubro a maio, que é o que as safras
# simuladas (semeadura em out-dez, ciclos de 110 a 150 dias) cobrem. Fora disso o resultado
# do modelo é extrapolação. O raio de 50 km é uma escolha conservadora: a grade da NASA
# POWER tem células de cerca de 50 a 60 km.
RAIO_DOMINIO_KM = 50
MESES_ANALISE_TREINO = (10, 11, 12, 1, 2, 3, 4, 5)

# Este protótipo atende propriedades no Brasil (caixa delimitadora aproximada).
BRASIL_LAT = (-34.0, 6.0)
BRASIL_LON = (-74.5, -28.0)

UFS = {
    "AC": "Acre", "AL": "Alagoas", "AP": "Amapá", "AM": "Amazonas", "BA": "Bahia", "CE": "Ceará",
    "DF": "Distrito Federal", "ES": "Espírito Santo", "GO": "Goiás", "MA": "Maranhão",
    "MT": "Mato Grosso", "MS": "Mato Grosso do Sul", "MG": "Minas Gerais", "PA": "Pará",
    "PB": "Paraíba", "PR": "Paraná", "PE": "Pernambuco", "PI": "Piauí", "RJ": "Rio de Janeiro",
    "RN": "Rio Grande do Norte", "RS": "Rio Grande do Sul", "RO": "Rondônia", "RR": "Roraima",
    "SC": "Santa Catarina", "SP": "São Paulo", "SE": "Sergipe", "TO": "Tocantins",
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

# Predição conformal (hidrica/conformal.py). A calibração usa ANOS_VALIDACAO, que por isso NÃO
# podem ser usados para ajustar o modelo final (ver treinar_e_avaliar).
CONFORMAL_ALFA = 0.10                  # nível de confiança de 90%: o conjunto contém a classe verdadeira em ~90% dos casos
CONFORMAL_METODO = "auto"              # "auto" | "lac" | "mondrian" | "aps"
# No modo "auto", usa-se Mondrian (garantia por classe) se, na calibração, alguma classe ficar abaixo disto com o LAC global.
CONFORMAL_COBERTURA_MINIMA_CLASSE = 0.85

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
