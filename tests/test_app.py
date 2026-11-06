import pandas as pd
import pytest

import app as modulo_app
import config
from app import MSG_SEM_MODELO, create_app
from hidrica import clima as mod_clima
from hidrica import recomendacao

FORM_OK = {
    "cultura": "milho", "solo": "médio",
    "data_semeadura": "2016-10-15", "data_analise": "2017-01-10",
    "data_irrigacao": "", "lamina_irrigacao": "",
}
HOJE = "2026-01-01"  # o clima sintético dos testes termina em 30/06/2025


@pytest.fixture(scope="module")
def pasta(modelo_treinado):
    return modelo_treinado[0]


@pytest.fixture(scope="module")
def cliente(clima, pasta):
    return create_app(pasta, clima=clima, atualizar=False, hoje=HOJE).test_client()


@pytest.mark.parametrize("rota", ["/", "/analise", "/metodologia", "/sobre"])
def test_paginas_respondem(cliente, rota):
    resp = cliente.get(rota)
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "HidroDecisão" in html and "Plataforma de análise" in html  # menu em todas as páginas


def test_inicio_tem_apresentacao_e_botao(cliente):
    html = cliente.get("/").get_data(as_text=True)
    assert "suporte à decisão" in html
    assert "Acessar a plataforma de análise" in html
    assert "ANA, 2021" in html


def test_rodape_mostra_ultima_data_do_clima(cliente):
    assert "Clima até 30/06/2025" in cliente.get("/").get_data(as_text=True)


def test_formulario_agrupado_por_categorias(cliente):
    html = cliente.get("/analise").get_data(as_text=True)
    assert "<form" in html
    for titulo in ["Informações da cultura", "Características do solo", "Ciclo da cultura",
                   "Última irrigação", "Data de referência da análise"]:
        assert titulo in html
    assert "Aguardando análise" in html


def test_data_padrao_e_limites_seguem_o_clima_disponivel(cliente):
    html = cliente.get("/analise").get_data(as_text=True)
    assert 'value="2025-06-30"' in html  # padrão = última data disponível
    assert 'max="2025-06-30"' in html and 'min="2010-01-01"' in html
    formulario = html.split('id="form-analise"')[1].split("</form>")[0]
    assert "2026" not in formulario  # nenhuma data futura


def test_data_padrao_nao_passa_de_hoje(clima, pasta):
    c = create_app(pasta, clima=clima, atualizar=False, hoje="2025-03-01").test_client()
    html = c.get("/analise").get_data(as_text=True)
    assert 'value="2025-03-01"' in html and 'max="2025-03-01"' in html


def test_get_com_parametros_preenche_o_formulario(cliente):
    html = cliente.get("/analise?cultura=soja&solo=argiloso&data_semeadura=2024-11-01").get_data(as_text=True)
    assert 'value="2024-11-01"' in html
    assert '<option value="soja" selected>' in html


def test_post_invalido_mostra_erro(cliente):
    resp = cliente.post("/analise", data={"cultura": "milho", "solo": "médio"})
    assert resp.status_code == 200
    assert "Informe a data de semeadura" in resp.get_data(as_text=True)


def test_post_com_data_alem_da_disponivel_explica_o_limite(cliente):
    resp = cliente.post("/analise", data={**FORM_OK, "data_semeadura": "2025-05-01", "data_analise": "2025-07-15"})
    assert "vão até 30/06/2025" in resp.get_data(as_text=True)


def test_post_valido_mostra_resultado_completo(cliente):
    html = cliente.post("/analise", data=FORM_OK).get_data(as_text=True)
    assert "Resultado da análise" in html
    assert any(texto in html for texto in config.NOMES_CLASSES.values())
    for bloco in ["Situação do solo", "Recomendações de manejo", "Clima da última semana", "Dados utilizados",
                  "Água no solo", "Irrigar quanto", "Chuva na semana", "Ver detalhes técnicos",
                  "Ver mais dados do clima", "Limitações"]:
        assert bloco in html
    assert html.count("data:image/png;base64") == 2
    assert "Recomendação de suporte à decisão" in html


def test_valores_digitados_sao_mantidos(cliente):
    html = cliente.post("/analise", data={**FORM_OK, "data_analise": "2016-10-01"}).get_data(as_text=True)
    assert 'value="2016-10-15"' in html
    assert "posterior à semeadura" in html


def test_metodologia_traz_fontes_criterios_e_limitacoes(cliente):
    html = cliente.get("/metodologia").get_data(as_text=True)
    for trecho in ["NASA POWER", "Não são medições de uma estação", "Defasagem", "Penman-Monteith", "Dr ≥ RAW",
                   "Rótulos simulados", "Random Forest", "não prova validade agronômica"]:
        assert trecho in html


def test_sobre_traz_contexto_e_equipe(cliente):
    html = cliente.get("/sobre").get_data(as_text=True)
    assert "Contexto acadêmico" in html and "Equipe de desenvolvimento" in html


def test_exemplos_da_pagina_inicial_sao_validos(cliente, clima):
    html = cliente.get("/").get_data(as_text=True)
    assert html.count('class="cartao exemplo"') >= 3
    for preset in modulo_app.PRESETS_HISTORICOS:
        _, erros = recomendacao.validar(preset, clima, HOJE)
        assert erros == [], (preset["titulo"], erros)


def test_exemplo_da_situacao_atual_usa_o_dado_mais_recente(clima, pasta):
    c = create_app(pasta, clima=clima, atualizar=False, hoje="2025-06-30").test_client()
    html = c.get("/").get_data(as_text=True)
    assert "Situação atual" in html and "data_analise=2025-06-30" in html


def test_sem_modelo(clima, tmp_path):
    c = create_app(tmp_path, clima=clima, atualizar=False, hoje=HOJE).test_client()
    assert MSG_SEM_MODELO in c.get("/analise").get_data(as_text=True)
    assert c.get("/").status_code == 200


def test_atualizar_dados_com_falha_mantem_dados(cliente, monkeypatch):
    def falha(*a, **k):
        raise OSError("sem internet")

    monkeypatch.setattr(mod_clima, "atualizar_clima", falha)
    html = cliente.post("/atualizar-dados", follow_redirects=True).get_data(as_text=True)
    assert "Não foi possível atualizar" in html
    assert "Clima até 30/06/2025" in html


def test_atualizar_dados_com_sucesso(clima, pasta, monkeypatch):
    extra = mod_clima.adicionar_et0(mod_clima.gerar_clima_sintetico("2025-07-01", "2025-07-20"))
    novo = pd.concat([clima, extra])
    monkeypatch.setattr(mod_clima, "atualizar_clima", lambda **k: novo)
    monkeypatch.setattr(mod_clima, "carregar_clima", lambda: novo)
    monkeypatch.setattr(mod_clima, "carregar_meta", lambda: {
        "atualizado_em": "2025-07-21T10:00:00", "fonte_nome": "NASA POWER (teste)", "tipo_dado": "teste"})
    c = create_app(pasta, clima=clima, atualizar=False, hoje="2025-07-21").test_client()
    html = c.post("/atualizar-dados", follow_redirects=True).get_data(as_text=True)
    assert "Dados climáticos de referência atualizados" in html
    assert "Clima até 20/07/2025" in html
    assert 'max="2025-07-20"' in html
