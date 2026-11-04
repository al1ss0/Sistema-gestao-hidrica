import numpy as np
import pandas as pd
import pandas.testing as pdt
import pytest

import config
from hidrica import clima as mod_clima


def test_colunas_e_sem_nan():
    df = mod_clima.gerar_clima_sintetico()
    assert list(df.columns) == ["tmax", "tmin", "ur", "vento", "rad", "chuva"]
    assert not df.isna().any().any()


def test_faixas(clima):
    assert clima["ur"].between(30, 100).all()
    assert (clima["chuva"] >= 0).all()


def test_et0_positivo(clima):
    assert (clima["et0"] > 0).all()


def test_mesma_seed_mesmo_resultado():
    pdt.assert_frame_equal(mod_clima.gerar_clima_sintetico(), mod_clima.gerar_clima_sintetico())


def _bruto(n, extra=None):
    """Série bruta no formato da NASA POWER (ausente = -999)."""
    idx = pd.date_range("2026-10-01", periods=n, freq="D", name="data")
    df = pd.DataFrame({"tmax": 25.0, "tmin": 12.0, "ur": 70.0, "vento": 2.0, "rad": 18.0, "chuva": 1.0}, index=idx)
    for (coluna, posicao), valor in (extra or {}).items():
        df.iloc[posicao, df.columns.get_loc(coluna)] = valor
    return df


def test_dias_finais_incompletos_sao_descartados_e_nao_preenchidos():
    # Radiação ainda indisponível nos 2 últimos dias; o último dia também sem chuva.
    bruto = _bruto(6, {("rad", 4): -999, ("rad", 5): -999, ("chuva", 5): -999})
    limpo = mod_clima._limpar(bruto)
    assert limpo.index.max() == pd.Timestamp("2026-10-04")
    assert len(limpo) == 4
    assert not limpo.isna().any().any()


def test_chuva_ausente_no_fim_nao_vira_zero():
    bruto = _bruto(5, {("chuva", 4): -999})
    # 5 dias a partir de 01/10; o dia 05/10 está sem chuva, então a série termina em 04/10.
    assert mod_clima._limpar(bruto).index.max() == pd.Timestamp("2026-10-04")


def test_lacunas_internas_sao_tratadas():
    bruto = _bruto(6, {("tmax", 2): -999, ("chuva", 3): -999})
    bruto.iloc[1, bruto.columns.get_loc("tmax")] = 20.0
    bruto.iloc[3, bruto.columns.get_loc("tmax")] = 30.0
    limpo = mod_clima._limpar(bruto)
    assert len(limpo) == 6
    assert limpo["tmax"].iloc[2] == pytest.approx(25.0)  # interpolação linear entre 20 e 30
    assert limpo["chuva"].iloc[3] == 0.0                  # lacuna interna de chuva vira 0 (spec)


def test_serie_sem_nenhum_dia_completo_levanta_erro():
    with pytest.raises(ValueError):
        mod_clima._limpar(_bruto(3, {("rad", 0): -999, ("rad", 1): -999, ("rad", 2): -999}))


@pytest.fixture
def pasta_dados(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    return tmp_path


def _falso_download(chamadas, ate, chuva=1.0):
    def falso(inicio, fim=None, timeout=60):
        chamadas.append((pd.Timestamp(inicio), pd.Timestamp(fim)))
        idx = pd.date_range(inicio, ate, freq="D", name="data")
        return pd.DataFrame({"tmax": 25.0, "tmin": 12.0, "ur": 70.0, "vento": 2.0, "rad": 18.0, "chuva": chuva}, index=idx)
    return falso


def test_primeira_atualizacao_baixa_tudo_e_grava_metadados(pasta_dados, monkeypatch):
    chamadas = []
    monkeypatch.setattr(mod_clima, "baixar_nasa_power", _falso_download(chamadas, "2026-10-29"))
    df = mod_clima.atualizar_clima(hoje="2026-11-03")
    assert chamadas[0][0] == pd.Timestamp(config.DATA_INICIO)
    assert df.index.max() == pd.Timestamp("2026-10-29")
    meta = mod_clima.carregar_meta()
    assert meta["ultima_data"] == "2026-10-29" and meta["fonte"] == "nasa_power"
    assert "não é medição de estação" in meta["tipo_dado"]
    assert "et0" in mod_clima.carregar_clima().columns


def test_atualizacao_incremental_preserva_historico_e_aplica_revisoes(pasta_dados, monkeypatch):
    base = mod_clima.adicionar_et0(mod_clima.gerar_clima_sintetico(fim="2026-09-30"))
    mod_clima._salvar(base, "nasa_power")
    chamadas = []
    monkeypatch.setattr(mod_clima, "baixar_nasa_power", _falso_download(chamadas, "2026-10-10", chuva=99.0))
    df = mod_clima.atualizar_clima(hoje="2026-10-12")

    corte = pd.Timestamp("2026-09-30") - pd.Timedelta(days=mod_clima.SOBREPOSICAO_DIAS)
    assert chamadas[0][0] == corte                        # só baixa o trecho recente
    assert df.index.is_unique and df.index.is_monotonic_increasing
    assert df.index.max() == pd.Timestamp("2026-10-10")
    antes = corte - pd.Timedelta(days=1)
    pdt.assert_frame_equal(df.loc[:antes], base.loc[:antes], check_freq=False)
    assert (df.loc[corte:, "chuva"] == 99.0).all()        # sobreposição revisada pela fonte
    assert not df.isna().any().any()


def test_falha_no_download_mantem_arquivo_atual(pasta_dados, monkeypatch):
    base = mod_clima.adicionar_et0(mod_clima.gerar_clima_sintetico(fim="2026-09-30"))
    mod_clima._salvar(base, "nasa_power")

    def quebra(*a, **k):
        raise OSError("sem internet")

    monkeypatch.setattr(mod_clima, "baixar_nasa_power", quebra)
    with pytest.raises(OSError):
        mod_clima.atualizar_clima(hoje="2026-10-12")
    assert mod_clima.carregar_meta()["ultima_data"] == "2026-09-30"
    assert mod_clima.carregar_clima().index.max() == pd.Timestamp("2026-09-30")


def test_clima_sintetico_nao_e_tratado_como_historico_real(pasta_dados, monkeypatch):
    mod_clima._salvar(mod_clima.adicionar_et0(mod_clima.gerar_clima_sintetico(fim="2026-09-30")), "sintetico")
    chamadas = []
    monkeypatch.setattr(mod_clima, "baixar_nasa_power", _falso_download(chamadas, "2026-10-10"))
    mod_clima.atualizar_clima(hoje="2026-10-12")
    assert chamadas[0][0] == pd.Timestamp(config.DATA_INICIO)  # rebaixa tudo em vez de misturar com o sintético
    assert mod_clima.carregar_meta()["fonte"] == "nasa_power"


# --- clima por ponto arbitrário (usado quando o agricultor escolhe outra localidade) -----------

import json  # noqa: E402

from hidrica import localidade  # noqa: E402

SORRISO = localidade.Localidade("Sorriso – MT", -12.545, -55.711, 363.0, "teste", "municipio")


class _Resposta:
    def __init__(self, corpo):
        self._corpo = json.dumps(corpo).encode()

    def read(self, *a):
        return self._corpo

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _corpo_nasa(dias, altitude=370.6, rad_ausente_nos_ultimos=0):
    idx = [d.strftime("%Y%m%d") for d in pd.date_range("2026-10-01", periods=dias)]
    param = {k: {d: v for d in idx} for k, v in
             {"T2M_MAX": 28.0, "T2M_MIN": 17.0, "RH2M": 75.0, "WS2M": 2.0, "ALLSKY_SFC_SW_DWN": 20.0, "PRECTOTCORR": 1.0}.items()}
    for d in idx[len(idx) - rad_ausente_nos_ultimos:]:
        param["ALLSKY_SFC_SW_DWN"][d] = -999.0
    return {"geometry": {"coordinates": [-55.711, -12.545, altitude]}, "properties": {"parameter": param}}


def test_consulta_usa_as_coordenadas_pedidas_e_le_a_altitude_da_grade(monkeypatch):
    urls = []

    def falso(url, timeout):
        urls.append(url)
        return _Resposta(_corpo_nasa(10))

    monkeypatch.setattr(mod_clima.urllib.request, "urlopen", falso)
    df, altitude = mod_clima._consultar_nasa(-12.545, -55.711, "2026-10-01", "2026-10-10", 30)
    assert "latitude=-12.54500" in urls[0] and "longitude=-55.71100" in urls[0]
    assert "start=20261001" in urls[0] and "end=20261010" in urls[0]
    assert altitude == pytest.approx(370.6) and len(df) == 10


def test_consulta_descarta_dias_sem_radiacao_no_fim(monkeypatch):
    monkeypatch.setattr(mod_clima.urllib.request, "urlopen",
                        lambda url, timeout: _Resposta(_corpo_nasa(10, rad_ausente_nos_ultimos=2)))
    df, _ = mod_clima._consultar_nasa(-12.5, -55.7, "2026-10-01", "2026-10-10", 30)
    assert df.index.max() == pd.Timestamp("2026-10-08")


def test_et0_depende_da_latitude_e_da_altitude(clima):
    base = clima[["tmax", "tmin", "ur", "vento", "rad", "chuva"]].tail(200)
    sul = mod_clima.adicionar_et0(base, -28.26, 687)["et0"]
    norte = mod_clima.adicionar_et0(base, -3.0, 20)["et0"]
    assert not np.allclose(sul, norte)
    alto = mod_clima.adicionar_et0(base, -28.26, 2000)["et0"]
    assert not np.allclose(sul, alto)


@pytest.fixture
def nasa_falsa(monkeypatch):
    mod_clima.limpar_cache()
    chamadas = []

    def falso(lat, lon, inicio, fim, timeout):
        chamadas.append((lat, lon, pd.Timestamp(inicio), pd.Timestamp(fim)))
        idx = pd.date_range(inicio, fim, freq="D", name="data")
        df = pd.DataFrame({"tmax": 28.0, "tmin": 17.0, "ur": 75.0, "vento": 2.0, "rad": 20.0, "chuva": 1.0}, index=idx)
        return df, 365.0

    monkeypatch.setattr(mod_clima, "_consultar_nasa", falso)
    yield chamadas
    mod_clima.limpar_cache()


def test_obter_janela_calcula_et0_com_a_altitude_da_localidade(nasa_falsa):
    df, altitude = mod_clima.obter_janela(SORRISO, "2026-10-01", "2026-10-10")
    assert altitude == 363.0 and (df["et0"] > 0).all() and len(df) == 10


def test_obter_janela_sem_altitude_usa_a_da_grade(nasa_falsa):
    sem_alt = localidade.Localidade("X", -12.5, -55.7, None, "x", "coordenadas")
    _, altitude = mod_clima.obter_janela(sem_alt, "2026-10-01", "2026-10-05")
    assert altitude == 365.0


def test_cache_evita_nova_consulta(nasa_falsa):
    mod_clima.obter_janela(SORRISO, "2026-10-01", "2026-10-10")
    mod_clima.obter_janela(SORRISO, "2026-10-01", "2026-10-10")
    assert len(nasa_falsa) == 1
    mod_clima.obter_janela(SORRISO, "2026-10-01", "2026-10-11")  # período diferente = nova consulta
    assert len(nasa_falsa) == 2


def test_cache_nao_deixa_o_chamador_alterar_o_valor_guardado(nasa_falsa):
    df, _ = mod_clima.obter_janela(SORRISO, "2026-10-01", "2026-10-10")
    df["chuva"] = 999
    de_novo, _ = mod_clima.obter_janela(SORRISO, "2026-10-01", "2026-10-10")
    assert (de_novo["chuva"] == 1.0).all()


def test_cache_expira(nasa_falsa, monkeypatch):
    relogio = {"t": 1000.0}
    monkeypatch.setattr(mod_clima.time, "monotonic", lambda: relogio["t"])
    mod_clima.obter_janela(SORRISO, "2026-10-01", "2026-10-10")
    relogio["t"] += mod_clima.TTL_CACHE_S + 1
    mod_clima.obter_janela(SORRISO, "2026-10-01", "2026-10-10")
    assert len(nasa_falsa) == 2


def test_cache_tem_tamanho_maximo(nasa_falsa, monkeypatch):
    monkeypatch.setattr(mod_clima, "MAX_ENTRADAS_CACHE", 3)
    for dia in range(2, 9):
        mod_clima.obter_janela(SORRISO, "2026-10-01", f"2026-10-{dia:02d}")
    assert len(mod_clima._cache) == 3


def test_ultima_data_completa(nasa_falsa):
    assert mod_clima.ultima_data_completa(SORRISO, "2026-11-03") == pd.Timestamp("2026-11-03")


def test_verificar_cobertura(clima):
    janela = clima.loc["2025-01-01":"2025-02-10"]
    assert mod_clima.verificar_cobertura(janela, "2025-01-01", "2025-02-10") is None
    assert "vão até 10/02/2025" in mod_clima.verificar_cobertura(janela, "2025-01-01", "2025-03-01")
    assert "começam em 01/01/2025" in mod_clima.verificar_cobertura(janela, "2024-12-01", "2025-02-10")
    assert "Não há dados" in mod_clima.verificar_cobertura(janela.iloc[0:0], "2025-01-01", "2025-02-10")
    com_buraco = janela.drop(janela.index[10])
    assert "dias sem dados" in mod_clima.verificar_cobertura(com_buraco, "2025-01-01", "2025-02-10")
