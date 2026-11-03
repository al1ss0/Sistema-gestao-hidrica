import pytest

import config
from app import MSG_SEM_MODELO, create_app

FORM_OK = {
    "cultura": "milho", "solo": "médio",
    "data_semeadura": "2016-10-15", "data_analise": "2017-01-10",
    "data_irrigacao": "", "lamina_irrigacao": "",
}


@pytest.fixture(scope="module")
def cliente(clima, modelo_treinado):
    pasta, _, _ = modelo_treinado
    return create_app(pasta, clima=clima).test_client()


def test_get_mostra_formulario(cliente):
    resp = cliente.get("/")
    assert resp.status_code == 200
    assert b"<form" in resp.data


def test_post_invalido_mostra_erro(cliente):
    resp = cliente.post("/", data={"cultura": "milho", "solo": "médio"})
    assert resp.status_code == 200
    assert "Informe a data de semeadura" in resp.get_data(as_text=True)


def test_post_valido_mostra_resultado(cliente):
    resp = cliente.post("/", data=FORM_OK)
    html = resp.get_data(as_text=True)
    assert resp.status_code == 200
    assert "Recomendação de suporte à decisão" in html
    assert "data:image/png;base64" in html
    assert any(texto in html for texto in config.NOMES_CLASSES.values())


def test_valores_digitados_sao_mantidos(cliente):
    resp = cliente.post("/", data={**FORM_OK, "data_analise": "2016-10-01"})
    html = resp.get_data(as_text=True)
    assert 'value="2016-10-15"' in html
    assert "posterior à semeadura" in html


def test_sem_modelo(clima, tmp_path):
    resp = create_app(tmp_path, clima=clima).test_client().get("/")
    assert MSG_SEM_MODELO in resp.get_data(as_text=True)
