"""Clima diário: download da NASA POWER, atualização incremental, clima sintético e ET0.

Os dados da NASA POWER são estimativas derivadas de reanálise/modelagem e de satélite,
não medições de estação meteorológica. Os dias mais recentes têm defasagem (a radiação
solar é a variável que demora mais) e podem ser revisados pela fonte.
"""
import json
import threading
import time
import urllib.request
from collections import OrderedDict
from datetime import date, datetime

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
# O clima sintético só serve para testes e demonstração sem internet.
FIM_SINTETICO_PADRAO = "2025-06-30"
SOBREPOSICAO_DIAS = 30  # dias já baixados que são baixados de novo, para receber revisões da fonte

DESCRICAO_FONTE = {
    "nasa_power": {
        "nome": "NASA POWER (série diária, ponto de Passo Fundo – RS)",
        "tipo": "Estimativa de reanálise/modelagem e satélite — não é medição de estação meteorológica",
    },
    "sintetico": {
        "nome": "Clima sintético gerado pelo sistema (apenas para testes)",
        "tipo": "Dados artificiais — não representam o clima real",
    },
}


def _hoje(hoje=None):
    return pd.Timestamp(hoje if hoje is not None else date.today()).normalize()


def _limpar(df):
    """Remove os dias finais ainda indisponíveis e trata lacunas internas.

    Dias recentes que a fonte ainda não calculou vêm como -999 em alguma variável. Esses
    dias NÃO são interpolados nem preenchidos: a série termina no último dia completo.
    """
    df = df[COLUNAS].replace(-999, np.nan)
    completo = df.notna().all(axis=1)
    if not completo.any():
        raise ValueError("A NASA POWER não retornou nenhum dia completo no período pedido.")
    df = df.loc[: completo[completo].index.max()].copy()
    df["chuva"] = df["chuva"].fillna(0.0)  # lacuna interna de chuva = 0 (spec.md, seção 4)
    df = df.interpolate(method="linear", limit_area="inside")
    return df


def _consultar_nasa(lat, lon, inicio, fim, timeout):
    """Consulta a NASA POWER para um ponto. Retorna (clima limpo, altitude da célula da grade ou None)."""
    inicio = pd.Timestamp(inicio)
    fim = _hoje(fim)
    url = URL_NASA.format(
        lon=f"{lon:.5f}", lat=f"{lat:.5f}",
        ini=inicio.strftime("%Y%m%d"), fim=fim.strftime("%Y%m%d"),
    )
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        resposta = json.load(resp)
    dados = resposta["properties"]["parameter"]
    df = pd.DataFrame({novo: pd.Series(dados[orig]) for orig, novo in MAPA_NASA.items()})
    df.index = pd.to_datetime(df.index, format="%Y%m%d")
    df.index.name = "data"
    coordenadas = (resposta.get("geometry") or {}).get("coordinates") or []
    altitude = float(coordenadas[2]) if len(coordenadas) > 2 else None
    return _limpar(df), altitude


def baixar_nasa_power(inicio=config.DATA_INICIO, fim=None, timeout=120, lat=config.LAT, lon=config.LON):
    """Baixa o clima diário de `inicio` até `fim` (padrão: hoje). A série termina no último dia completo."""
    return _consultar_nasa(lat, lon, inicio, fim, timeout)[0]


def gerar_clima_sintetico(inicio=config.DATA_INICIO, fim=FIM_SINTETICO_PADRAO, seed=config.SEED):
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
    return pd.DataFrame(
        {"tmax": tmax, "tmin": tmin, "ur": ur, "vento": vento, "rad": rad, "chuva": chuva},
        index=pd.Index(datas, name="data"),
    )


def adicionar_et0(df, lat=config.LAT, alt=config.ALT):
    df = df.copy()
    df["et0"] = agro.et0(
        df["tmax"], df["tmin"], df["ur"], df["vento"], df["rad"],
        lat, alt, df.index.dayofyear,
    )
    return df


def _salvar(df, fonte):
    """Grava o clima e os metadados (fonte, tipo do dado, última data, momento da atualização)."""
    config.DATA_DIR.mkdir(exist_ok=True)
    df.to_csv(config.DATA_DIR / "clima.csv")
    (config.DATA_DIR / "fonte_clima.txt").write_text(fonte, encoding="utf-8")
    meta = {
        "fonte": fonte,
        "fonte_nome": DESCRICAO_FONTE[fonte]["nome"],
        "tipo_dado": DESCRICAO_FONTE[fonte]["tipo"],
        "primeira_data": df.index.min().date().isoformat(),
        "ultima_data": df.index.max().date().isoformat(),
        "atualizado_em": datetime.now().isoformat(timespec="seconds"),
    }
    (config.DATA_DIR / "clima_meta.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return meta


def preparar_clima(sintetico=False, hoje=None):
    """Reconstrói todo o clima (usado pelo pipeline). Sem internet, cai no clima sintético."""
    df, fonte = None, "sintetico"
    if not sintetico:
        try:
            df = baixar_nasa_power(config.DATA_INICIO, hoje)
            fonte = "nasa_power"
        except Exception as erro:  # sem internet, API fora do ar, formato inesperado
            print(f"AVISO: falha ao baixar a NASA POWER ({erro}).")
    if df is None:
        print("AVISO: usando clima sintético")
        df = gerar_clima_sintetico(fim=_hoje(hoje))
    df = adicionar_et0(df)
    _salvar(df, fonte)
    return df


def carregar_clima():
    return pd.read_csv(config.DATA_DIR / "clima.csv", index_col="data", parse_dates=["data"])


def carregar_meta():
    """Metadados do clima salvo, ou None se ainda não existirem."""
    arquivo = config.DATA_DIR / "clima_meta.json"
    if not arquivo.exists():
        return None
    return json.loads(arquivo.read_text(encoding="utf-8"))


def atualizar_clima(hoje=None, timeout=60):
    """Atualização incremental: baixa só o trecho recente e preserva o histórico já salvo.

    Os últimos SOBREPOSICAO_DIAS dias são baixados de novo, porque a fonte pode revisar
    valores provisórios. Levanta exceção se o download falhar (o arquivo atual é mantido).
    """
    hoje = _hoje(hoje)
    meta = carregar_meta()
    arquivo_fonte = config.DATA_DIR / "fonte_clima.txt"
    if meta:
        fonte_atual = meta.get("fonte")
    else:  # arquivos gerados antes de existir o clima_meta.json
        fonte_atual = arquivo_fonte.read_text(encoding="utf-8").strip() if arquivo_fonte.exists() else None
    existente = None
    if fonte_atual == "nasa_power":
        try:
            existente = carregar_clima()
        except FileNotFoundError:
            existente = None
    inicio = config.DATA_INICIO if existente is None else existente.index.max() - pd.Timedelta(days=SOBREPOSICAO_DIAS)
    novo = adicionar_et0(baixar_nasa_power(inicio, hoje, timeout))
    if existente is None:
        df = novo
    else:
        antes = existente[existente.index < novo.index.min()]
        depois = existente[existente.index > novo.index.max()]
        df = pd.concat([antes, novo, depois])
    _salvar(df, "nasa_power")
    return df


# --- Clima sob demanda para qualquer localidade (usado pelo app) ---------------------------------

TTL_CACHE_S = 6 * 3600       # os dias recentes podem ser revisados pela fonte
MAX_ENTRADAS_CACHE = 128     # limite de memória: o cache fica na RAM e não cresce sem controle
_cache = OrderedDict()
_trava = threading.Lock()


def limpar_cache():
    with _trava:
        _cache.clear()


def _cache_obter(chave):
    with _trava:
        item = _cache.get(chave)
        if item is None:
            return None
        instante, valor = item
        if time.monotonic() - instante > TTL_CACHE_S:
            del _cache[chave]
            return None
        _cache.move_to_end(chave)
        return valor


def _cache_guardar(chave, valor):
    with _trava:
        _cache[chave] = (time.monotonic(), valor)
        _cache.move_to_end(chave)
        while len(_cache) > MAX_ENTRADAS_CACHE:
            _cache.popitem(last=False)


def obter_janela(local, inicio, fim, timeout=60):
    """Clima diário (com ET0) de `inicio` a `fim` para a localidade. Retorna (DataFrame, altitude usada).

    A altitude é a da localidade; se ela não for conhecida, usa a da célula da grade da NASA POWER.
    """
    inicio, fim = pd.Timestamp(inicio).normalize(), pd.Timestamp(fim).normalize()
    chave = (round(local.lat, 2), round(local.lon, 2), local.alt, inicio, fim)
    valor = _cache_obter(chave)
    if valor is None:
        bruto, altitude_grade = _consultar_nasa(local.lat, local.lon, inicio, fim, timeout)
        altitude = local.alt if local.alt is not None else altitude_grade
        if altitude is None:
            raise ValueError("Não foi possível determinar a altitude da localidade.")
        valor = (adicionar_et0(bruto, local.lat, altitude), altitude)
        _cache_guardar(chave, valor)
    return valor[0].copy(), valor[1]


def ultima_data_completa(local, hoje=None, timeout=30):
    """Último dia com todas as variáveis disponíveis na fonte para a localidade."""
    hoje = _hoje(hoje)
    df, _ = obter_janela(local, hoje - pd.Timedelta(days=20), hoje, timeout)
    return df.index.max()


def _br(ts):
    return pd.Timestamp(ts).strftime("%d/%m/%Y")


def verificar_cobertura(df, inicio, fim):
    """Mensagem de erro se `df` não cobre todo o período de `inicio` a `fim`; None se cobre."""
    inicio, fim = pd.Timestamp(inicio), pd.Timestamp(fim)
    if df is None or df.empty:
        return "Não há dados climáticos para este período nesta localidade."
    if df.index.max() < fim:
        return (f"Os dados climáticos desta localidade vão até {_br(df.index.max())}: a fonte tem alguns dias de "
                "defasagem. Escolha uma data da análise até lá.")
    if df.index.min() > inicio:
        return f"Os dados climáticos desta localidade começam em {_br(df.index.min())}. Escolha uma semeadura a partir dessa data."
    if len(df.loc[inicio:fim]) != (fim - inicio).days + 1:
        return "Há dias sem dados climáticos no período informado nesta localidade."
    return None
