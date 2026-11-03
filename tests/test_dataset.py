import numpy as np
import pandas as pd

from hidrica import agro, dataset


def _cenario(clima, politica="irrigado", cultura="milho", solo="arenoso"):
    rng = np.random.default_rng(42)
    return dataset.simular_cenario(clima, cultura, solo, "2015-10-01", politica, rng=rng)


def test_dr_entre_zero_e_taw(clima):
    sim = _cenario(clima)
    assert (sim["dr"] >= 0).all()
    assert (sim["dr"] <= sim["taw"] + 1e-9).all()


def test_sequeiro_nao_irriga(clima):
    sim = _cenario(clima, politica="sequeiro")
    assert (sim["irrigacao"] == 0).all()


def test_tamanho_do_ciclo(clima):
    sim = _cenario(clima)
    assert len(sim) == agro.duracao_ciclo("milho")


def test_politica_irrigado_irriga_algumas_vezes(clima):
    assert (_cenario(clima)["irrigacao"] > 0).any()


def test_features_nao_usam_dias_futuros(clima):
    base = dataset.adicionar_features(_cenario(clima))
    data_futura = pd.Timestamp("2015-10-01") + pd.Timedelta(days=100)
    alterado = clima.copy()
    alterado.loc[data_futura, "chuva"] += 80
    mudou = dataset.adicionar_features(_cenario(alterado))
    pdt_cols = dataset.NUMERICAS
    antes = base.loc[base["d"] == 50, pdt_cols].reset_index(drop=True)
    depois = mudou.loc[mudou["d"] == 50, pdt_cols].reset_index(drop=True)
    pd.testing.assert_frame_equal(antes, depois)


def test_proibidas_fora_das_features():
    assert not set(dataset.PROIBIDAS) & set(dataset.FEATURES)


def test_divisao_por_anos_sem_sobreposicao():
    df = pd.DataFrame({"ano": list(range(2010, 2025)), "classe": 0})
    treino, validacao, teste = dataset.dividir(df)
    anos = [set(treino["ano"]), set(validacao["ano"]), set(teste["ano"])]
    assert not anos[0] & anos[1] and not anos[0] & anos[2] and not anos[1] & anos[2]
    assert sum(len(a) for a in anos) == 15
