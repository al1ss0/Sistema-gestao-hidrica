import pytest

from hidrica import modelo as mod_modelo
from hidrica import recomendacao

FORM_OK = {
    "cultura": "milho", "solo": "médio",
    "data_semeadura": "2016-10-15", "data_analise": "2017-01-10",
    "data_irrigacao": "", "lamina_irrigacao": "",
}


def test_sem_semeadura_gera_erro(clima):
    entrada, erros = recomendacao.validar({**FORM_OK, "data_semeadura": ""}, clima)
    assert entrada is None and any("semeadura" in e for e in erros)


def test_analise_antes_da_semeadura(clima):
    _, erros = recomendacao.validar({**FORM_OK, "data_analise": "2016-10-01"}, clima)
    assert any("posterior" in e for e in erros)


def test_irrigacao_sem_lamina(clima):
    _, erros = recomendacao.validar({**FORM_OK, "data_irrigacao": "2016-12-20"}, clima)
    assert any("lâmina" in e for e in erros)


def test_analise_apos_fim_do_ciclo(clima):
    _, erros = recomendacao.validar({**FORM_OK, "data_analise": "2017-06-01"}, clima)
    assert any("ciclo" in e for e in erros)


def test_formulario_valido_gera_recomendacao(clima, modelo_treinado):
    pasta, _, _ = modelo_treinado
    pipe, metadata = mod_modelo.carregar_modelo(pasta)
    entrada, erros = recomendacao.validar(FORM_OK, clima)
    assert erros == []
    res = recomendacao.recomendar(entrada, clima, pipe, metadata)
    for chave in ["classe_modelo", "texto_modelo", "probabilidades", "classe_referencia",
                  "texto_referencia", "divergente", "dr", "raw", "lamina", "grafico", "aviso"]:
        assert chave in res
    assert sum(res["probabilidades"].values()) == pytest.approx(100, abs=0.5)
    assert isinstance(res["grafico"], str) and res["grafico"]


def test_irrigacao_informada_e_usada(clima, modelo_treinado):
    pasta, _, _ = modelo_treinado
    pipe, metadata = mod_modelo.carregar_modelo(pasta)
    form = {**FORM_OK, "data_irrigacao": "2017-01-09", "lamina_irrigacao": "30"}
    entrada, erros = recomendacao.validar(form, clima)
    assert erros == []
    sem_irrigacao, _ = recomendacao.validar(FORM_OK, clima)
    com = recomendacao.recomendar(entrada, clima, pipe, metadata)
    sem = recomendacao.recomendar(sem_irrigacao, clima, pipe, metadata)
    assert com["dr"] <= sem["dr"]
