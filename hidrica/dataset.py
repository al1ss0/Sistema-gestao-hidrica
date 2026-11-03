"""Simulação de safras, features e dataset rotulado (spec.md, seção 7)."""
import numpy as np
import pandas as pd

import config
from hidrica import agro

CATEGORICAS = ["cultura", "solo"]
NUMERICAS = [
    "dias_apos_semeadura", "kc",
    "et0_7d", "etc_7d", "chuva_7d", "chuva_14d",
    "tmax_7d", "ur_7d", "vento_7d", "rad_7d",
    "dias_desde_chuva", "dias_desde_irrigacao", "lamina_ultima_irrigacao",
    "etc_menos_chuva_desde_irrigacao",
]
FEATURES = CATEGORICAS + NUMERICAS
PROIBIDAS = ["dr", "taw", "raw"]


def simular_cenario(clima, cultura, solo, semeadura, politica, rng=None, irrigacoes=None, data_fim=None):
    """Balanço hídrico diário de um cenário. politica: sequeiro, irrigado ou manual."""
    semeadura = pd.Timestamp(semeadura)
    if data_fim is None:
        fim = semeadura + pd.Timedelta(days=agro.duracao_ciclo(cultura) - 1)
    else:
        fim = pd.Timestamp(data_fim)
    janela = clima.loc[semeadura:fim]
    taw = agro.taw(cultura, solo)
    raw = agro.raw(cultura, solo)
    irrigacoes = {pd.Timestamp(k): v for k, v in (irrigacoes or {}).items()}

    linhas = []
    dr_ant = 0.0
    for d, (data, dia) in enumerate(janela.iterrows()):
        kc = agro.kc(cultura, d)
        etc = kc * dia["et0"]
        if politica == "irrigado":
            irr = dr_ant if (dr_ant >= raw and rng.random() < 0.5) else 0.0
        elif politica == "manual":
            irr = float(irrigacoes.get(data, 0.0))
        else:
            irr = 0.0
        dr = min(max(dr_ant - dia["chuva"] - irr + etc, 0.0), taw)
        linhas.append((data, d, cultura, solo, kc, dia["et0"], etc, dia["chuva"], irr,
                       dia["tmax"], dia["ur"], dia["vento"], dia["rad"], dr, taw, raw,
                       agro.classificar(dr, raw)))
        dr_ant = dr
    colunas = ["data", "d", "cultura", "solo", "kc", "et0", "etc", "chuva", "irrigacao",
               "tmax", "ur", "vento", "rad", "dr", "taw", "raw", "classe"]
    return pd.DataFrame(linhas, columns=colunas)


def adicionar_features(df):
    """Features de um cenário. Cada linha usa apenas o próprio dia e os anteriores."""
    df = df.copy()
    df["dias_apos_semeadura"] = df["d"]
    for col, nome in [("et0", "et0_7d"), ("etc", "etc_7d"), ("chuva", "chuva_7d")]:
        df[nome] = df[col].rolling(7, min_periods=1).sum()
    df["chuva_14d"] = df["chuva"].rolling(14, min_periods=1).sum()
    for col in ["tmax", "ur", "vento", "rad"]:
        df[f"{col}_7d"] = df[col].rolling(7, min_periods=1).mean()

    chuva = df["chuva"].to_numpy()
    irr = df["irrigacao"].to_numpy()
    saldo = (df["etc"] - df["chuva"]).to_numpy()
    n = len(df)
    desde_chuva = np.empty(n)
    desde_irr = np.empty(n)
    lamina = np.empty(n)
    acum = np.empty(n)
    ultima_chuva = ultima_irr = None
    lam = 0.0
    soma = 0.0
    for i in range(n):
        if chuva[i] >= config.CHUVA_MIN:
            ultima_chuva = i
        if irr[i] > 0:
            ultima_irr = i
            lam = irr[i]
            soma = 0.0
        soma += saldo[i]
        desde_chuva[i] = config.MAX_DIAS if ultima_chuva is None else min(i - ultima_chuva, config.MAX_DIAS)
        desde_irr[i] = config.MAX_DIAS if ultima_irr is None else min(i - ultima_irr, config.MAX_DIAS)
        lamina[i] = lam
        acum[i] = soma
    df["dias_desde_chuva"] = desde_chuva
    df["dias_desde_irrigacao"] = desde_irr
    df["lamina_ultima_irrigacao"] = lamina
    df["etc_menos_chuva_desde_irrigacao"] = acum
    return df


def gerar_dataset(clima, salvar=True):
    rng = np.random.default_rng(config.SEED)
    partes = []
    cenario_id = 0
    for cultura in config.CULTURAS:
        for solo in config.SOLOS:
            for mes, dia in config.DATAS_SEMEADURA:
                for ano in config.ANOS_SEMEADURA:
                    for politica in ("sequeiro", "irrigado"):
                        semeadura = pd.Timestamp(year=ano, month=mes, day=dia)
                        sim = simular_cenario(clima, cultura, solo, semeadura, politica, rng=rng)
                        sim = adicionar_features(sim)
                        sim = sim[(sim["d"] >= 14) & (sim["d"] % 3 == 0)].copy()
                        sim["cenario_id"] = cenario_id
                        sim["ano"] = ano
                        sim["politica"] = politica
                        partes.append(sim)
                        cenario_id += 1
    df = pd.concat(partes, ignore_index=True)
    colunas = FEATURES + ["classe", "cenario_id", "ano", "politica", "data"]
    df = df[colunas]
    if salvar:
        config.DATA_DIR.mkdir(exist_ok=True)
        df.to_csv(config.DATA_DIR / "dataset.csv", index=False)
    return df


def dividir(df):
    treino = df[df["ano"].isin(list(config.ANOS_TREINO))]
    validacao = df[df["ano"].isin(list(config.ANOS_VALIDACAO))]
    teste = df[df["ano"].isin(list(config.ANOS_TESTE))]
    return treino, validacao, teste
