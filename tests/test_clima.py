import pandas.testing as pdt

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
