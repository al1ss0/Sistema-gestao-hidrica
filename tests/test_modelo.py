import numpy as np
import pandas as pd

from hidrica import dataset, modelo


def test_metricas_csv_tem_5_linhas(modelo_treinado):
    pasta, _, _ = modelo_treinado
    metricas = pd.read_csv(pasta / "reports" / "metricas.csv")
    assert list(metricas["modelo"]) == ["RegressaoLogistica", "RandomForest", "XGBoost", "MLP", "Dummy"]
    assert metricas["selecionado"].sum() == 1


def test_metadata_tem_as_chaves(modelo_treinado):
    pasta, _, _ = modelo_treinado
    _, metadata = modelo.carregar_modelo(pasta)
    for chave in ["modelo", "hiperparametros", "features", "metricas", "data"]:
        assert chave in metadata
    assert metadata["features"] == dataset.FEATURES


def test_predict_proba_soma_1(modelo_treinado):
    pasta, df, _ = modelo_treinado
    pipe, _ = modelo.carregar_modelo(pasta)
    proba = pipe.predict_proba(df[dataset.FEATURES].head(50))
    assert proba.shape == (50, 3)
    assert np.allclose(proba.sum(axis=1), 1.0, atol=1e-6)


def test_treino_rapido_e_reprodutivel(modelo_treinado, tmp_path):
    pasta, df, _ = modelo_treinado
    modelo.treinar_e_avaliar(df, tmp_path, rapido=True)
    a = (pasta / "reports" / "metricas.csv").read_text()
    b = (tmp_path / "reports" / "metricas.csv").read_text()
    assert a == b
