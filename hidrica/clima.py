"""Clima diário: download da NASA POWER, clima sintético e ET0 (spec.md, seção 4)."""
import json
import urllib.request

import numpy as np
import pandas as pd

import config
from hidrica import agro

URL_NASA = (
    "https://power.larc.nasa.gov/api/temporal/daily/point"
    "?parameters=T2M_MAX,T2M_MIN,RH2M,WS2M,ALLSKY_SFC_SW_DWN,PRECTOTCORR"
    "&community=AG&longitude={lon}&latitude={lat}&start={ini}&end={fim}&format=JSON"
)

COLUNAS = ["tmax", "tmin", "ur", "vento", "rad", "chuva"]
MAPA_NASA = {
    "T2M_MAX": "tmax",
    "T2M_MIN": "tmin",
    "RH2M": "ur",
    "WS2M": "vento",
    "ALLSKY_SFC_SW_DWN": "rad",
    "PRECTOTCORR": "chuva",
}


def baixar_nasa_power():
    url = URL_NASA.format(
        lon=config.LON,
        lat=config.LAT,
        ini=config.DATA_INICIO.replace("-", ""),
        fim=config.DATA_FIM.replace("-", ""),
    )
    with urllib.request.urlopen(url, timeout=120) as resp:
        dados = json.load(resp)["properties"]["parameter"]
    df = pd.DataFrame({novo: pd.Series(dados[orig]) for orig, novo in MAPA_NASA.items()})
    df.index = pd.to_datetime(df.index, format="%Y%m%d")
    df.index.name = "data"
    df = df.replace(-999, np.nan)
    if df.empty:
        raise ValueError("A NASA POWER retornou uma resposta vazia.")
    df["chuva"] = df["chuva"].fillna(0.0)
    df = df.interpolate(method="linear", limit_direction="both")
    return df[COLUNAS]


def gerar_clima_sintetico(inicio=config.DATA_INICIO, fim=config.DATA_FIM, seed=config.SEED):
    rng = np.random.default_rng(seed)
    datas = pd.date_range(inicio, fim, freq="D")
    n = len(datas)
    doy = datas.dayofyear.to_numpy()
    s = np.cos(2 * np.pi * (doy - 15) / 365)
    tmax = 24 + 6 * s + rng.normal(0, 2, n)
    tmin = tmax - 10 + rng.normal(0, 1, n)
    ur = np.clip(75 + rng.normal(0, 8, n), 30, 100)
    vento = 2 + np.abs(rng.normal(0, 0.7, n))
    rad = np.clip(18 + 7 * s + rng.normal(0, 2, n), 2, 32)
    chove = rng.random(n) < 0.3
    chuva = np.where(chove, rng.exponential(15, n), 0.0)
    df = pd.DataFrame(
        {"tmax": tmax, "tmin": tmin, "ur": ur, "vento": vento, "rad": rad, "chuva": chuva},
        index=pd.Index(datas, name="data"),
    )
    return df


def adicionar_et0(df):
    df = df.copy()
    df["et0"] = agro.et0(
        df["tmax"], df["tmin"], df["ur"], df["vento"], df["rad"],
        config.LAT, config.ALT, df.index.dayofyear,
    )
    return df


def preparar_clima(sintetico=False):
    fonte = "sintetico"
    df = None
    if not sintetico:
        try:
            df = baixar_nasa_power()
            fonte = "nasa_power"
        except Exception as erro:  # sem internet, API fora do ar, formato inesperado
            print(f"AVISO: falha ao baixar a NASA POWER ({erro}).")
    if df is None:
        print("AVISO: usando clima sintético")
        df = gerar_clima_sintetico()
    df = adicionar_et0(df)
    config.DATA_DIR.mkdir(exist_ok=True)
    df.to_csv(config.DATA_DIR / "clima.csv")
    (config.DATA_DIR / "fonte_clima.txt").write_text(fonte, encoding="utf-8")
    return df


def carregar_clima():
    return pd.read_csv(config.DATA_DIR / "clima.csv", index_col="data", parse_dates=["data"])
