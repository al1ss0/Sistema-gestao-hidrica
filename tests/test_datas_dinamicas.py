"""Validação de datas sem data máxima fixa e análises com dados recentes."""
import pandas as pd
import pytest

from hidrica import clima as mod_clima
from hidrica import modelo as mod_modelo
from hidrica import recomendacao

FORM_2026 = {"cultura": "milho", "solo": "médio", "data_semeadura": "2026-09-15", "data_analise": "2026-10-29"}
FORM_HISTORICO = {"cultura": "milho", "solo": "médio", "data_semeadura": "2016-10-15", "data_analise": "2017-01-10"}


@pytest.fixture(scope="module")
def clima_2026():
    """Clima que vai até 29/10/2026, como a fonte real na data deste desenvolvimento."""
    return mod_clima.adicionar_et0(mod_clima.gerar_clima_sintetico(fim="2026-10-29"))


def test_aceita_datas_de_2026_quando_o_clima_as_cobre(clima_2026):
    entrada, erros = recomendacao.validar(FORM_2026, clima_2026, hoje="2026-11-03")
    assert erros == [] and entrada is not None


def test_limite_superior_acompanha_o_clima_carregado(clima):
    # O mesmo formulário é recusado quando o clima carregado termina em 30/06/2025.
    _, erros = recomendacao.validar(FORM_2026, clima, hoje="2026-11-03")
    assert any("vão até 30/06/2025" in e for e in erros)


def test_data_posterior_a_hoje_e_recusada(clima_2026):
    _, erros = recomendacao.validar({**FORM_2026, "data_analise": "2026-11-20"}, clima_2026, hoje="2026-11-03")
    assert any("não pode ser posterior à data atual" in e for e in erros)


def test_data_apos_a_ultima_do_clima_mas_antes_de_hoje_explica_a_defasagem(clima_2026):
    _, erros = recomendacao.validar({**FORM_2026, "data_analise": "2026-11-02"}, clima_2026, hoje="2026-11-03")
    assert any("vão até 29/10/2026" in e and "defasagem" in e for e in erros)


def test_limites_de_datas_usam_o_menor_entre_clima_e_hoje(clima_2026):
    assert recomendacao.limites_datas(clima_2026, "2026-11-03")[1] == pd.Timestamp("2026-10-29")
    assert recomendacao.limites_datas(clima_2026, "2026-10-01")[1] == pd.Timestamp("2026-10-01")


def test_semeadura_antes_do_inicio_do_clima_e_recusada(clima_2026):
    form = {**FORM_2026, "data_semeadura": "2009-10-01", "data_analise": "2009-12-01"}
    _, erros = recomendacao.validar(form, clima_2026, hoje="2026-11-03")
    assert any("anterior ao início dos dados climáticos" in e for e in erros)


def test_irrigacao_fora_do_periodo_e_recusada(clima_2026):
    form = {**FORM_2026, "data_irrigacao": "2026-11-01", "lamina_irrigacao": "20"}
    _, erros = recomendacao.validar(form, clima_2026, hoje="2026-11-03")
    assert any("entre a semeadura e a data da análise" in e for e in erros)


def test_analise_historica_continua_funcionando(clima_2026):
    entrada, erros = recomendacao.validar(FORM_HISTORICO, clima_2026, hoje="2026-11-03")
    assert erros == [] and entrada["analise"] == pd.Timestamp("2017-01-10")


def test_recomendacao_com_dados_recentes(clima_2026, modelo_treinado):
    pasta, _, _ = modelo_treinado
    pipe, metadata = mod_modelo.carregar_modelo(pasta)
    entrada, erros = recomendacao.validar(FORM_2026, clima_2026, hoje="2026-11-03")
    assert erros == []
    res = recomendacao.recomendar(entrada, clima_2026, pipe, metadata)
    assert res["entrada"]["analise"] == "29/10/2026"
    assert res["dias_apos_semeadura"] == 44
    assert res["estagio"] == "Desenvolvimento"
    assert res["agua_disponivel"] == pytest.approx(res["taw"] - res["dr"], abs=0.11)
    assert 0 <= res["pct_esgotada"] <= 100
    assert res["grafico_ciclo"] and res["recomendacoes"]
