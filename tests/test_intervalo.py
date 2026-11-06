"""Intervalos de predição no modelo e no site: cobertura, conjunto nunca vazio e exibição dentro/fora do domínio."""
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import config
from app import create_app
from hidrica import conformal, dataset, localidade
from hidrica import modelo as mod_modelo
from hidrica import recomendacao
from test_apresentacao import com, parte_do_solo, renderizar, sem_detalhes

RAIZ = Path(__file__).resolve().parents[1]
FORM = {"cultura": "milho", "solo": "médio", "data_semeadura": "2016-10-15", "data_analise": "2017-01-10"}
FORM_JULHO = {"cultura": "milho", "solo": "médio", "data_semeadura": "2016-06-10", "data_analise": "2016-07-20"}
HOJE = "2026-01-01"
SORRISO = localidade.Localidade("Sorriso – MT", -12.545, -55.711, 363.0, "teste", "municipio")


@pytest.fixture(scope="module")
def pasta(modelo_treinado):
    return modelo_treinado[0]


@pytest.fixture(scope="module")
def carregado(pasta):
    return mod_modelo.carregar_modelo(pasta)


@pytest.fixture(scope="module")
def aplicacao(clima, pasta):
    return create_app(pasta, clima=clima, atualizar=False, hoje=HOJE, limite_por_minuto=0)


def analisar(clima, carregado, form=FORM, local=None):
    pipe, metadata = carregado
    entrada, erros = recomendacao.validar(form, clima, HOJE)
    assert erros == []
    return recomendacao.recomendar(entrada, clima, pipe, metadata, local)


@pytest.fixture(scope="module")
def res_dentro(clima, carregado):
    return analisar(clima, carregado)


def intervalo(confiavel, outras=(), **extra):
    base = {"disponivel": True, "motivo": None, "metodo": "mondrian", "nivel_pct": 90,
            "anos_calibracao": [2020, 2021], "anos_teste": [2022, 2023, 2024],
            "cobertura_teste_pct": 93.5, "tamanho_medio_teste": 1.14,
            "conjunto": [0] + [1] * len(outras), "textos_conjunto": ["Sem necessidade de irrigação", *outras],
            "confiavel": confiavel, "outras": list(outras)}
    base.update(extra)
    return base


# --- o modelo calibrado --------------------------------------------------------------------------

def test_calibracao_usa_os_anos_de_validacao_e_o_modelo_nunca_os_viu(carregado):
    _, metadata = carregado
    spec = metadata["conformal"]
    assert spec["anos_calibracao"] == sorted(config.ANOS_VALIDACAO)
    assert spec["anos_teste"] == sorted(config.ANOS_TESTE)
    ajuste = set(metadata["anos_ajuste_do_modelo"])
    assert ajuste and ajuste <= set(config.ANOS_TREINO)
    assert not ajuste & set(spec["anos_calibracao"])   # o modelo não viu os anos de calibração
    assert not ajuste & set(spec["anos_teste"])


def test_nivel_e_configuravel_em_config(carregado):
    spec = carregado[1]["conformal"]
    assert spec["alfa"] == pytest.approx(config.CONFORMAL_ALFA) and spec["nivel"] == pytest.approx(1 - config.CONFORMAL_ALFA)
    assert spec["metodo"] in conformal.METODOS


def test_cobertura_no_teste_fica_dentro_da_tolerancia(carregado):
    av = carregado[1]["conformal"]["avaliacao_teste"]
    nivel = 1 - config.CONFORMAL_ALFA
    assert nivel - 0.04 <= av["cobertura"] <= nivel + 0.08, av["cobertura"]
    assert av["n"] > 1000


def test_tamanhos_nunca_zero_e_somam_100_por_cento(carregado):
    av = carregado[1]["conformal"]["avaliacao_teste"]
    assert set(av["distribuicao_tamanhos"]) == {"1", "2", "3"}  # não existe tamanho 0
    assert sum(av["distribuicao_tamanhos"].values()) == pytest.approx(1.0)
    assert 1.0 <= av["tamanho_medio"] <= 3.0


def test_relatorio_conformal_csv(pasta):
    tabela = pd.read_csv(pasta / "reports" / "conformal.csv")
    assert list(tabela["metodo"]) == ["lac", "mondrian", "aps"]
    assert tabela["usado"].sum() == 1
    for coluna in ["cobertura_teste", "tamanho_medio_teste", "pct_tamanho_1_teste", "cobertura_classe_0_teste",
                   "cobertura_classe_1_teste", "cobertura_classe_2_teste", "cobertura_classe_1_calibracao"]:
        assert coluna in tabela.columns
    assert (tabela["tamanho_medio_teste"] >= 1).all()


def test_conjunto_nunca_vazio_e_contem_o_resultado_do_modelo(carregado, modelo_treinado):
    pipe, metadata = carregado
    df = modelo_treinado[1].sample(1500, random_state=1)
    proba = pipe.predict_proba(df[dataset.FEATURES])
    mascara = conformal.conjunto_de_predicao(proba, metadata["conformal"])
    assert (mascara.sum(axis=1) >= 1).all()
    assert mascara[np.arange(len(df)), proba.argmax(axis=1)].all()


# --- artefatos publicados no repositório ---------------------------------------------------------

def test_artefatos_publicados_tem_calibracao_valida():
    metadata = json.loads((RAIZ / "models" / "metadata.json").read_text(encoding="utf-8"))
    spec = metadata["conformal"]
    assert spec["anos_calibracao"] == sorted(config.ANOS_VALIDACAO)
    assert not set(metadata["anos_ajuste_do_modelo"]) & set(spec["anos_calibracao"])
    av = spec["avaliacao_teste"]
    assert abs(av["cobertura"] - (1 - config.CONFORMAL_ALFA)) <= 0.05, av["cobertura"]
    assert 1.0 <= av["tamanho_medio"] <= 1.5
    # a cobertura por classe fica perto da meta: nenhuma classe mal coberta
    assert min(v for v in av["cobertura_por_classe"].values()) >= 1 - config.CONFORMAL_ALFA - 0.05


@pytest.mark.skipif(not (RAIZ / "data" / "dataset.csv").exists(), reason="dataset.csv não existe (não vai para o git)")
def test_numeros_publicados_conferem_com_o_modelo_publicado():
    """Reconta a cobertura com o modelo e o dataset reais: os números dos relatórios não podem ser inventados."""
    pipe, metadata = mod_modelo.carregar_modelo(RAIZ)
    spec = metadata["conformal"]
    _, validacao, teste = dataset.dividir(pd.read_csv(RAIZ / "data" / "dataset.csv"))
    av = conformal.avaliar(pipe.predict_proba(teste[dataset.FEATURES]), teste["classe"], spec)
    assert av["cobertura"] == pytest.approx(spec["avaliacao_teste"]["cobertura"], abs=1e-9)
    assert av["tamanho_medio"] == pytest.approx(spec["avaliacao_teste"]["tamanho_medio"], abs=1e-9)
    # recalibrando com os mesmos dados sai o mesmo limiar
    nova = conformal.calibrar(pipe.predict_proba(validacao[dataset.FEATURES]), validacao["classe"],
                              spec["classes"], spec["alfa"], spec["metodo"])
    assert nova["q_hat"] == pytest.approx(spec["q_hat"])


# --- dentro do domínio: o resultado vem do modelo e o intervalo aparece --------------------------

def test_dentro_do_dominio_o_intervalo_esta_disponivel(res_dentro):
    iv = res_dentro["intervalo"]
    assert not res_dentro["fora_do_dominio"] and iv["disponivel"]
    assert res_dentro["classe_modelo"] in iv["conjunto"]
    assert iv["confiavel"] == (len(iv["conjunto"]) == 1)
    assert iv["nivel_pct"] == round((1 - config.CONFORMAL_ALFA) * 100)


def test_o_conjunto_da_tela_e_o_do_metodo(res_dentro, clima, carregado):
    pipe, metadata = carregado
    entrada, _ = recomendacao.validar(FORM, clima, HOJE)
    linha = recomendacao.dataset.adicionar_features(recomendacao.dataset.simular_cenario(
        clima, entrada["cultura"], entrada["solo"], entrada["semeadura"], "manual", data_fim=entrada["analise"])).iloc[[-1]]
    proba = pipe.predict_proba(linha[metadata["features"]])
    esperado = [int(c) for c, d in zip(pipe.classes_, conformal.conjunto_de_predicao(proba, metadata["conformal"])[0]) if d]
    assert res_dentro["intervalo"]["conjunto"] == esperado


def test_linha_confiavel(aplicacao, res_dentro):
    html = renderizar(aplicacao, com(res_dentro, intervalo=intervalo(True)))
    assert re.search(r'<span class="simbolo" aria-hidden="true">✓</span> Resultado confiável</p>', html)
    assert "Resultado incerto" not in html


def test_linha_incerta_com_uma_outra_classe(aplicacao, res_dentro):
    html = renderizar(aplicacao, com(res_dentro, intervalo=intervalo(False, ["Atenção: irrigação em breve"])))
    assert ("⚠</span> Resultado incerto: pode ser também “Atenção: irrigação em breve”. "
            "Observe a lavoura antes de decidir.") in html
    assert "Resultado confiável" not in html


def test_linha_incerta_com_duas_outras_classes(aplicacao, res_dentro):
    outras = ["Atenção: irrigação em breve", "Irrigação recomendada"]
    html = renderizar(aplicacao, com(res_dentro, intervalo=intervalo(False, outras)))
    assert "pode ser também “Atenção: irrigação em breve” ou “Irrigação recomendada”. Observe a lavoura" in html


def test_linha_fica_logo_abaixo_do_resultado(aplicacao, res_dentro):
    html = renderizar(aplicacao, com(res_dentro, intervalo=intervalo(True)))
    assert html.index('class="faixa-resultado') < html.index('class="confianca') < html.index('class="kpis-grandes"')


def test_tela_principal_nao_tem_termos_tecnicos_do_intervalo(aplicacao, res_dentro):
    html = renderizar(aplicacao, com(res_dentro, intervalo=intervalo(False, ["Irrigação recomendada"])))
    visivel = re.sub(r"<[^>]+>", " ", sem_detalhes(parte_do_solo(html)))
    for termo in ["conformal", "cobertura", "Cobertura", "Conjunto de predição", "90%", "calibra", "Mondrian"]:
        assert termo not in visivel, termo


def test_detalhes_tecnicos_trazem_conjunto_nivel_e_cobertura_do_teste(aplicacao, res_dentro):
    html = renderizar(aplicacao, com(res_dentro, intervalo=intervalo(False, ["Atenção: irrigação em breve"])))
    detalhes = re.search(r"<summary>Ver detalhes técnicos</summary>(.*?)</details>", html, re.S).group(1)
    texto = re.sub(r"<[^>]+>", " ", detalhes)
    for esperado in ["Conjunto de predição", "Sem necessidade de irrigação · Atenção: irrigação em breve",
                     "Nível de confiança", "90%", "Mondrian", "Cobertura medida no teste (2022–2024)", "93.5%",
                     "tamanho médio do conjunto: 1.14"]:
        assert esperado in texto, esperado


# --- fora do domínio: o resultado vem do FAO-56 e o intervalo NÃO é mostrado ---------------------

def test_fora_do_dominio_por_localidade_nao_tem_intervalo(clima, carregado):
    res = analisar(clima, carregado, local=SORRISO)
    iv = res["intervalo"]
    assert res["fora_do_dominio"] and res["origem_principal"] == "referência"
    assert iv["disponivel"] is False and iv["motivo"] == "fora_do_dominio" and iv["motivos"]
    assert "conjunto" not in iv and "confiavel" not in iv


def test_fora_do_dominio_por_epoca_nao_tem_intervalo(clima, carregado):
    res = analisar(clima, carregado, form=FORM_JULHO)
    assert res["fora_do_dominio"] and res["intervalo"]["disponivel"] is False
    assert any("outubro–maio" in m for m in res["intervalo"]["motivos"])


@pytest.mark.parametrize("quando", ["localidade", "epoca"])
def test_fora_do_dominio_a_tela_nao_mostra_confianca_e_os_detalhes_explicam(aplicacao, clima, carregado, quando):
    res = analisar(clima, carregado, **({"local": SORRISO} if quando == "localidade" else {"form": FORM_JULHO}))
    html = renderizar(aplicacao, res)
    assert 'class="confianca' not in html
    assert "Resultado confiável" not in html and "Resultado incerto" not in html
    detalhes = re.sub(r"<[^>]+>", " ", re.search(r"<summary>Ver detalhes técnicos</summary>(.*?)</details>", html, re.S).group(1))
    for esperado in ["Intervalo de predição", "Não mostrado", "fora do domínio", "cálculo FAO-56", "garantia de cobertura",
                     "90%", res["intervalo"]["motivos"][0]]:
        assert esperado in detalhes, esperado
    assert "Conjunto de predição" not in detalhes and "Cobertura medida no teste" not in detalhes


# --- modelo sem calibração (arquivo antigo) ------------------------------------------------------

def test_modelo_sem_calibracao_nao_quebra_a_tela(aplicacao, clima, carregado):
    pipe, metadata = carregado
    sem = {k: v for k, v in metadata.items() if k != "conformal"}
    entrada, _ = recomendacao.validar(FORM, clima, HOJE)
    res = recomendacao.recomendar(entrada, clima, pipe, sem)
    assert res["intervalo"] == {"disponivel": False, "motivo": "sem_calibracao"}
    html = renderizar(aplicacao, res)
    assert 'class="confianca' not in html and "este modelo não tem calibração conforme" in html


# --- pelo site de verdade ------------------------------------------------------------------------

def test_site_dentro_do_dominio_mostra_exatamente_uma_das_duas_linhas(aplicacao):
    html = aplicacao.test_client().post("/analise", data=FORM).get_data(as_text=True)
    confiavel, incerto = "Resultado confiável" in html, "Resultado incerto" in html
    assert confiavel != incerto  # uma e só uma
    assert html.count('class="confianca') == 1


def test_site_fora_do_dominio_nao_mostra_nenhuma_linha(aplicacao, monkeypatch):
    from hidrica import clima as mod_clima
    from hidrica import localidade as mod_local

    monkeypatch.setattr(mod_local, "buscar_municipios",
                        lambda texto, uf=None, timeout=10: [{"nome": "Sorriso", "uf": "MT", "lat": -12.545, "lon": -55.711, "alt": 363.0}])
    monkeypatch.setattr(mod_clima, "obter_janela",
                        lambda local, ini, fim, timeout=60: (_CLIMA.loc[pd.Timestamp(ini):pd.Timestamp(fim)].copy(), 363.0))
    dados = {**FORM, "data_semeadura": "2024-10-10", "data_analise": "2025-01-20", "local_modo": "municipio", "municipio": "Sorriso"}
    html = aplicacao.test_client().post("/analise", data=dados).get_data(as_text=True)
    assert "Resultado da análise" in html and "Consulta fora do domínio do modelo" in html
    assert 'class="confianca' not in html
    assert "Não mostrado" in html


_CLIMA = None


@pytest.fixture(autouse=True)
def _guarda_clima(clima):
    global _CLIMA
    _CLIMA = clima
