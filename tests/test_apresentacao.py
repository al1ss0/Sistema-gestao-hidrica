"""Apresentação simplificada do resultado: poucos cartões, letras grandes e nenhum termo técnico à vista."""
import copy
import re
from pathlib import Path

import pytest
from flask import render_template

import config
from app import create_app
from hidrica import agro
from hidrica import modelo as mod_modelo
from hidrica import recomendacao

FORM_OK = {
    "cultura": "milho", "solo": "médio",
    "data_semeadura": "2016-10-15", "data_analise": "2017-01-10",
    "data_irrigacao": "", "lamina_irrigacao": "",
}
HOJE = "2026-01-01"
CSS = (Path(__file__).resolve().parents[1] / "static" / "css" / "style.css").read_text(encoding="utf-8")
SIGLAS = re.compile(r"\b(Dr|RAW|TAW|Kc|ETc|ET0)\b")


@pytest.fixture(scope="module")
def pasta(modelo_treinado):
    return modelo_treinado[0]


@pytest.fixture(scope="module")
def aplicacao(clima, pasta):
    return create_app(pasta, clima=clima, atualizar=False, hoje=HOJE, limite_por_minuto=0)


@pytest.fixture(scope="module")
def resultado_base(clima, pasta):
    pipe, metadata = mod_modelo.carregar_modelo(pasta)
    entrada, erros = recomendacao.validar(FORM_OK, clima, HOJE)
    assert erros == []
    return recomendacao.recomendar(entrada, clima, pipe, metadata)


def renderizar(aplicacao, res):
    """Renderiza a página com um resultado montado à mão, para cobrir todos os casos da tela."""
    culturas = {n: {**c, "ciclo": agro.duracao_ciclo(n)} for n, c in config.CULTURAS.items()}
    with aplicacao.test_request_context("/analise"):
        return render_template(
            "analise.html", pagina="analise", form={}, erros=[], res=res, aviso_modelo=None,
            data_min="2010-01-01", data_max="2025-06-30", modelo_nome="XGBoost", culturas=culturas,
            solos=config.SOLOS, ufs=config.UFS, metricas=None, msg_atualizacao=None, presets=[],
            permite_atualizar=False,
        )


def com(res, **campos):
    novo = copy.deepcopy(res)
    for chave, valor in campos.items():
        if chave.startswith("clima_"):
            novo["clima"][chave.removeprefix("clima_")] = valor
        else:
            novo[chave] = valor
    return novo


def parte_do_solo(html):
    """Do primeiro cartão até antes das recomendações (cartões do solo + barra)."""
    return html.split('<div class="kpis-grandes">', 1)[1].split("Recomendações de manejo", 1)[0]


def parte_do_clima(html):
    return html.split("Clima da última semana", 1)[1].split("Dados utilizados", 1)[0]


def sem_detalhes(trecho):
    return re.sub(r"<details>.*?</details>", "", trecho, flags=re.S)


def detalhes(trecho, titulo):
    achado = re.search(rf"<details>\s*<summary>{titulo}</summary>(.*?)</details>", trecho, re.S)
    assert achado, f"não achei o bloco “{titulo}”"
    return achado.group(1)


# --- cartões do solo -----------------------------------------------------------------------------

def test_tres_cartoes_grandes_do_solo(aplicacao, resultado_base):
    visivel = sem_detalhes(parte_do_solo(renderizar(aplicacao, resultado_base)))
    assert visivel.count('class="kpi-grande"') == 3
    for rotulo in ["Água no solo", "Irrigar quanto", "Chuva na semana"]:
        assert f'<div class="nome">{rotulo}</div>' in visivel
        assert len(rotulo.split()) <= 3


def test_nenhuma_sigla_a_vista_nos_cartoes_nem_na_barra(aplicacao, resultado_base):
    visivel = sem_detalhes(parte_do_solo(renderizar(aplicacao, resultado_base)))
    texto = re.sub(r"<[^>]+>", " ", visivel)  # só o texto que a pessoa lê
    assert not SIGLAS.search(texto), SIGLAS.search(texto)
    for velho in ["TAW =", "alerta ", "estresse (RAW)", "Déficit", "Lâmina líquida"]:
        assert velho not in texto
    assert not re.search(r"(?<![\d.])0 mm", texto)  # o "0 mm" da escala antiga (e não o de "130 mm")


def test_porcentagem_de_agua_restante_confere_com_o_calculo(aplicacao, resultado_base):
    res = resultado_base
    html = renderizar(aplicacao, res)
    esperado = round(100 - res["pct_esgotada"])
    assert re.search(rf'Água no solo</div>\s*<div class="valor">{esperado}<small>%</small>', html)
    assert f"{res['agua_disponivel']:g} mm de {res['taw']:g} mm" in html


@pytest.mark.parametrize("esgotada, restante", [(0, 100), (1.6, 98), (30, 70), (90, 10), (100, 0), (130, 0)])
def test_porcentagem_e_arredondada_e_limitada(aplicacao, resultado_base, esgotada, restante):
    html = renderizar(aplicacao, com(resultado_base, pct_esgotada=esgotada))
    assert re.search(rf'Água no solo</div>\s*<div class="valor">{restante}<small>%</small>', html)


def test_irrigar_quanto_mostra_a_lamina_quando_ha_necessidade(aplicacao, resultado_base):
    html = renderizar(aplicacao, com(resultado_base, lamina=41.2))
    assert re.search(r'Irrigar quanto</div>\s*<div class="valor">41\.2<small>mm</small>', html)
    assert "Não precisa" not in parte_do_solo(html)


def test_irrigar_quanto_diz_nao_precisa_em_vez_de_traco(aplicacao, resultado_base):
    visivel = sem_detalhes(parte_do_solo(renderizar(aplicacao, com(resultado_base, lamina=None))))
    assert re.search(r'Irrigar quanto</div>\s*<div class="valor texto">Não precisa</div>', visivel)
    assert "—" not in visivel


@pytest.mark.parametrize("chuva, texto", [(67.3, "67"), (0.4, "0"), (0.5, "1"), (12.5, "13"), (13.5, "14"), (100.0, "100")])
def test_chuva_da_semana_vem_arredondada(aplicacao, resultado_base, chuva, texto):
    html = renderizar(aplicacao, com(resultado_base, clima_chuva_7d=chuva))
    assert re.search(rf'Chuva na semana</div>\s*<div class="valor">{texto}<small>mm</small>', html)
    assert "nos últimos 7 dias" in html


# --- barra do solo -------------------------------------------------------------------------------

@pytest.mark.parametrize("nivel, rotulo", [
    (0, "Solo com água suficiente"), (1, "Atenção: irrigar em breve"), (2, "Irrigar agora"),
])
def test_barra_tem_cor_e_texto_conforme_a_situacao(aplicacao, resultado_base, nivel, rotulo):
    html = renderizar(aplicacao, com(resultado_base, classe_referencia=nivel, pct_esgotada=30))
    assert f'class="enchimento n{nivel}"' in html
    assert re.search(rf'<p class="situacao s{nivel}">.*?<span>{rotulo}</span>', html, re.S)
    assert f"Água no solo: 70%. {rotulo}" in html  # leitor de tela


def test_barra_mostra_a_agua_que_resta_e_nao_o_deficit(aplicacao, resultado_base):
    cheia = renderizar(aplicacao, com(resultado_base, pct_esgotada=10))
    seca = renderizar(aplicacao, com(resultado_base, pct_esgotada=90))
    assert 'class="enchimento n' in cheia and "width: 90%" in cheia
    assert "width: 10%" in seca


def test_barra_sem_linhas_tracejadas_e_com_texto_curto(aplicacao, resultado_base):
    html = renderizar(aplicacao, resultado_base)
    assert "marca-limite" not in html and "medidor" not in html
    assert "Quanto mais cheia, mais água tem no solo." in html
    assert "A barra representa a água disponível total" not in html


# --- detalhes técnicos ---------------------------------------------------------------------------

def test_detalhes_tecnicos_ficam_fechados_com_todos_os_valores(aplicacao, resultado_base):
    res = resultado_base
    corpo = parte_do_solo(renderizar(aplicacao, res))
    assert "<details>" in corpo and "<details open" not in corpo  # fechado por padrão
    dentro = re.sub(r"<[^>]+>", " ", detalhes(corpo, "Ver detalhes técnicos"))
    for esperado in [f"{res['dr']} mm", f"{res['alerta']} mm", f"{res['raw']} mm", f"{res['taw']} mm",
                     f"{res['agua_disponivel']} mm", f"{res['pct_esgotada']} %", str(res["kc"]), res["estagio"]]:
        assert esperado in dentro, esperado
    for sigla in ["Dr", "RAW", "TAW", "Kc"]:
        assert sigla in dentro  # o técnico ainda encontra tudo


# --- clima da última semana ----------------------------------------------------------------------

def test_clima_tem_titulo_e_tres_cartoes_grandes(aplicacao, resultado_base):
    clima_html = parte_do_clima(renderizar(aplicacao, resultado_base))
    visivel = sem_detalhes(clima_html)
    assert "Resumo dos últimos 7 dias." in visivel
    assert "fonte de dados" not in clima_html and "Indicadores climáticos" not in clima_html
    assert visivel.count('class="kpi-grande"') == 3
    for rotulo in ["Calor", "Dias sem chuva", "Última irrigação"]:
        assert f'<div class="nome">{rotulo}</div>' in visivel
    assert "Chuva em 7 dias" not in clima_html  # a chuva da semana já está nos cartões do solo


@pytest.mark.parametrize("temperatura, texto", [(20.8, "21"), (20.5, "21"), (20.4, "20"), (-1.5, "-1"), (-0.2, "0")])
def test_calor_vem_arredondado(aplicacao, resultado_base, temperatura, texto):
    html = renderizar(aplicacao, com(resultado_base, clima_tmax_7d=temperatura))
    assert re.search(rf'Calor</div>\s*<div class="valor">{texto}<small>°C</small>', html)


@pytest.mark.parametrize("dias, esperado", [
    (5, '5<small>dias</small>'), (1, '1<small>dia</small>'), (0, '0<small>dias</small>'), (60, '60+<small>dias</small>'),
])
def test_dias_sem_chuva(aplicacao, resultado_base, dias, esperado):
    html = renderizar(aplicacao, com(resultado_base, clima_dias_desde_chuva=dias))
    assert f'Dias sem chuva</div>\n            <div class="valor">{esperado}' in html


@pytest.mark.parametrize("dias, esperado", [
    (None, '<div class="valor texto">Não informada</div>'),
    (0, '<div class="valor texto">Hoje</div>'),
    (1, '<div class="valor">1<small>dia atrás</small></div>'),
    (15, '<div class="valor">15<small>dias atrás</small></div>'),
    (60, '<div class="valor">60+<small>dias atrás</small></div>'),
])
def test_ultima_irrigacao(aplicacao, resultado_base, dias, esperado):
    html = renderizar(aplicacao, com(resultado_base, clima_dias_desde_irrigacao=dias))
    assert re.search(rf'Última irrigação</div>\s*{re.escape(esperado)}', parte_do_clima(html))


def test_mais_dados_do_clima_ficam_fechados_com_os_nomes_tecnicos(aplicacao, resultado_base):
    res = resultado_base
    clima_html = parte_do_clima(renderizar(aplicacao, res))
    assert "<details open" not in clima_html
    dentro = re.sub(r"<[^>]+>", " ", detalhes(clima_html, "Ver mais dados do clima"))
    for esperado in ["Chuva em 14 dias", f"{res['clima']['chuva_14d']} mm", "(ET0)", f"{res['clima']['et0_7d']} mm",
                     "(ETc)", f"{res['clima']['etc_7d']} mm", "Umidade relativa", "Vento médio", "Radiação solar"]:
        assert esperado in dentro, esperado


# --- pelo site de verdade ------------------------------------------------------------------------

def test_pagina_real_usa_a_nova_apresentacao(aplicacao):
    html = aplicacao.test_client().post("/analise", data=FORM_OK).get_data(as_text=True)
    assert html.count('class="kpi-grande"') == 6  # 3 do solo + 3 do clima
    assert "Ver detalhes técnicos" in html and "Ver mais dados do clima" in html
    assert "Situação hídrica atual do solo" not in html


# --- tamanhos e celular (CSS) --------------------------------------------------------------------

def regra(seletor):
    achado = re.search(re.escape(seletor) + r"\s*\{([^}]*)\}", CSS)
    assert achado, seletor
    return achado.group(1)


def rem(corpo, propriedade):
    return float(re.search(rf"{propriedade}:\s*([\d.]+)rem", corpo).group(1))


def test_letras_grandes_nos_cartoes():
    assert rem(regra(".kpi-grande .valor"), "font-size") >= 2.5
    assert rem(regra(".kpi-grande .nome"), "font-size") >= 1.1
    assert rem(regra(".kpi-grande .sub"), "font-size") >= 1.0


def test_barra_alta():
    assert int(re.search(r"height:\s*(\d+)px", regra(".barra-solo")).group(1)) >= 28


def test_no_celular_os_cartoes_ficam_um_embaixo_do_outro():
    assert "grid-template-columns: 1fr;" in regra(".kpis-grandes")  # padrão = uma coluna
    tres = re.search(r"@media \(min-width: (\d+)px\) \{ \.kpis-grandes \{ grid-template-columns: repeat\(3, 1fr\); \} \}", CSS)
    assert tres and int(tres.group(1)) >= 600  # três colunas só em telas largas


def test_as_tres_cores_da_barra_existem():
    for n, cor in [(0, "#2e7d32"), (1, "#f2b200"), (2, "#c62828")]:
        assert cor in regra(f".enchimento.n{n}")
