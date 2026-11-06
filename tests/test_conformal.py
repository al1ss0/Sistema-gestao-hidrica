"""Predição conformal: propriedades matemáticas do método (sem depender do modelo do projeto)."""
import json

import numpy as np
import pytest

from hidrica import conformal

CLASSES = [0, 1, 2]


def dados_calibrados(n, semente, concentracao=(2.0, 1.0, 0.7)):
    """Probabilidades perfeitamente calibradas: o rótulo é sorteado da própria distribuição."""
    rng = np.random.default_rng(semente)
    proba = rng.dirichlet(concentracao, size=n)
    y = np.minimum((rng.random(n)[:, None] > proba.cumsum(axis=1)).sum(axis=1), len(concentracao) - 1)
    return proba, y


# --- quantil com correção de amostra finita ------------------------------------------------------

def test_quantil_e_a_k_esima_menor_pontuacao():
    scores = np.arange(1, 100) / 100  # n = 99
    assert conformal.quantil_conforme(scores, 0.10) == pytest.approx(0.90)  # k = ceil(100 * 0.9) = 90
    assert conformal.quantil_conforme(scores[::-1], 0.10) == pytest.approx(0.90)  # não depende da ordem


def test_quantil_nao_sofre_com_erro_de_ponto_flutuante():
    # (n+1)*(1-alfa) = 10 * 0.9 = 9 exato; um ceil ingênuo poderia dar 10
    assert conformal.quantil_conforme(np.arange(1, 10) / 10, 0.10) == pytest.approx(0.9)


def test_quantil_com_poucos_dados_inclui_todas_as_classes():
    assert conformal.quantil_conforme(np.array([0.1, 0.2, 0.3, 0.4, 0.5]), 0.10) == 1.0  # k = 6 > n = 5
    assert conformal.quantil_conforme(np.array([]), 0.10) == 1.0


@pytest.mark.parametrize("alfa", [0, 1, -0.1, 1.5])
def test_alfa_invalido(alfa):
    with pytest.raises(ValueError):
        conformal.quantil_conforme(np.array([0.1, 0.2]), alfa)
    with pytest.raises(ValueError):
        conformal.calibrar(np.full((3, 3), 1 / 3), [0, 1, 2], CLASSES, alfa)


def test_metodo_desconhecido():
    with pytest.raises(ValueError):
        conformal.calibrar(np.full((3, 3), 1 / 3), [0, 1, 2], CLASSES, 0.1, "magia")
    with pytest.raises(ValueError):
        conformal.conjunto_de_predicao(np.full((1, 3), 1 / 3), {"metodo": "magia", "q_hat": 0.5})


# --- cobertura -----------------------------------------------------------------------------------

@pytest.mark.parametrize("alfa", [0.05, 0.10, 0.20])
@pytest.mark.parametrize("metodo", ["lac", "aps"])
def test_cobertura_marginal_fica_perto_do_nivel(alfa, metodo):
    p_cal, y_cal = dados_calibrados(5000, 1)
    p_te, y_te = dados_calibrados(40000, 2)
    spec = conformal.calibrar(p_cal, y_cal, CLASSES, alfa, metodo)
    cobertura = conformal.avaliar(p_te, y_te, spec)["cobertura"]
    assert 1 - alfa - 0.012 <= cobertura <= 1 - alfa + 0.06, (metodo, alfa, cobertura)


def test_cobertura_garantida_mesmo_com_poucos_dados_de_calibracao():
    """Média sobre várias calibrações pequenas: a garantia vale na média (n = 99, alfa = 0.1)."""
    p_te, y_te = dados_calibrados(30000, 99)
    coberturas = []
    for semente in range(40):
        p_cal, y_cal = dados_calibrados(99, 1000 + semente)
        spec = conformal.calibrar(p_cal, y_cal, CLASSES, 0.10, "lac")
        coberturas.append(conformal.avaliar(p_te, y_te, spec)["cobertura"])
    assert np.mean(coberturas) >= 0.90 - 0.01


def test_mondrian_corrige_a_cobertura_por_classe():
    """Se uma classe é mais difícil, o LAC global a cobre menos; o Mondrian garante cada classe."""
    # classe 1 sistematicamente mal separada das demais
    rng = np.random.default_rng(7)

    def gerar(n):
        y = rng.choice(3, size=n, p=[0.55, 0.20, 0.25])
        logits = rng.normal(0, 1, (n, 3))
        logits[np.arange(n), y] += np.where(y == 1, 1.0, 3.0)  # sinal fraco para a classe 1
        p = np.exp(logits) / np.exp(logits).sum(axis=1, keepdims=True)
        return p, y

    p_cal, y_cal = gerar(8000)
    p_te, y_te = gerar(40000)
    lac = conformal.avaliar(p_te, y_te, conformal.calibrar(p_cal, y_cal, CLASSES, 0.10, "lac"))
    mon = conformal.avaliar(p_te, y_te, conformal.calibrar(p_cal, y_cal, CLASSES, 0.10, "mondrian"))
    assert lac["cobertura_por_classe"]["1"] < 0.80          # LAC global deixa a classe difícil mal coberta
    for c in "012":
        assert mon["cobertura_por_classe"][c] >= 0.90 - 0.02, (c, mon["cobertura_por_classe"])
    assert mon["tamanho_medio"] >= lac["tamanho_medio"]    # o preço: conjuntos maiores


# --- o conjunto nunca fica vazio e tem a forma esperada --------------------------------------------

ENTRADAS_DIFICEIS = np.array([
    [1 / 3, 1 / 3, 1 / 3],      # empate total
    [1.0, 0.0, 0.0],            # certeza
    [0.34, 0.33, 0.33],
    [0.0, 0.0, 1.0],
    [0.5, 0.5, 0.0],            # empate no topo
])


@pytest.mark.parametrize("metodo", ["lac", "mondrian", "aps"])
@pytest.mark.parametrize("q", [0.0, 0.01, 0.5, 0.99, 1.0])
def test_conjunto_nunca_e_vazio_e_contem_a_classe_mais_provavel(metodo, q):
    spec = {"metodo": metodo, "q_hat": [q, q, q] if metodo == "mondrian" else q, "classes": CLASSES}
    aleatorias = np.random.default_rng(3).dirichlet((0.3, 0.3, 0.3), size=2000)
    for proba in (ENTRADAS_DIFICEIS, aleatorias):
        mascara = conformal.conjunto_de_predicao(proba, spec)
        assert mascara.shape == proba.shape and mascara.dtype == bool
        assert (mascara.sum(axis=1) >= 1).all()
        assert mascara[np.arange(len(proba)), proba.argmax(axis=1)].all()


def test_conjunto_com_q_maximo_inclui_tudo():
    mascara = conformal.conjunto_de_predicao(ENTRADAS_DIFICEIS, {"metodo": "lac", "q_hat": 1.0, "classes": CLASSES})
    assert mascara.all()


@pytest.mark.parametrize("metodo", ["lac", "aps"])
def test_conjuntos_sao_cortes_da_ordem_de_probabilidade(metodo):
    """Quem está no conjunto nunca é menos provável do que quem ficou de fora."""
    p_cal, y_cal = dados_calibrados(3000, 4)
    spec = conformal.calibrar(p_cal, y_cal, CLASSES, 0.10, metodo)
    proba = np.random.default_rng(5).dirichlet((1, 1, 1), size=3000)
    dentro = conformal.conjunto_de_predicao(proba, spec)
    for p, m in zip(proba, dentro):
        if m.any() and (~m).any():
            assert p[m].min() >= p[~m].max()


def test_menor_alfa_gera_conjuntos_maiores_ou_iguais():
    p_cal, y_cal = dados_calibrados(5000, 6)
    proba = np.random.default_rng(8).dirichlet((1, 1, 1), size=2000)
    anterior = None
    for alfa in (0.30, 0.20, 0.10, 0.05, 0.01):
        spec = conformal.calibrar(p_cal, y_cal, CLASSES, alfa, "lac")
        mascara = conformal.conjunto_de_predicao(proba, spec)
        if anterior is not None:
            assert (mascara >= anterior).all()
        anterior = mascara


def test_mondrian_com_classe_ausente_na_calibracao_inclui_essa_classe():
    proba = np.array([[0.7, 0.2, 0.1]] * 400)
    y = np.array([0] * 400)  # classes 1 e 2 nunca aparecem
    spec = conformal.calibrar(proba, y, CLASSES, 0.10, "mondrian")
    assert spec["q_hat"][1] == 1.0 and spec["q_hat"][2] == 1.0
    assert conformal.conjunto_de_predicao(np.array([[0.7, 0.2, 0.1]]), spec).all()


# --- avaliação e especificação -------------------------------------------------------------------

def test_avaliar_devolve_numeros_coerentes():
    p, y = dados_calibrados(4000, 9)
    spec = conformal.calibrar(p, y, CLASSES, 0.10, "lac")
    av = conformal.avaliar(p, y, spec)
    assert av["n"] == 4000
    assert sum(av["distribuicao_tamanhos"].values()) == pytest.approx(1.0)
    media = sum(int(k) * v for k, v in av["distribuicao_tamanhos"].items())
    assert av["tamanho_medio"] == pytest.approx(media)
    assert set(av["cobertura_por_classe"]) == {"0", "1", "2"}
    assert 1 <= av["tamanho_medio"] <= 3


def test_avaliar_classe_ausente_devolve_none():
    proba = np.array([[0.8, 0.1, 0.1], [0.6, 0.3, 0.1]])
    spec = conformal.calibrar(np.tile(proba, (50, 1)), np.zeros(100, dtype=int), CLASSES, 0.10, "lac")
    assert conformal.avaliar(proba, np.array([0, 0]), spec)["cobertura_por_classe"]["1"] is None


def test_especificacao_sobrevive_ao_json_e_da_o_mesmo_resultado():
    p_cal, y_cal = dados_calibrados(3000, 10)
    proba = np.random.default_rng(11).dirichlet((1, 1, 1), size=500)
    for metodo in conformal.METODOS:
        spec = conformal.calibrar(p_cal, y_cal, CLASSES, 0.10, metodo)
        de_volta = json.loads(json.dumps(spec))
        assert (conformal.conjunto_de_predicao(proba, spec) == conformal.conjunto_de_predicao(proba, de_volta)).all()
        assert spec["nivel"] == pytest.approx(0.90) and spec["n_calibracao"] == 3000 and spec["classes"] == CLASSES


def test_proba_em_float32_da_o_mesmo_conjunto_que_em_float64():
    """predict_proba do XGBoost devolve float32; calibrar e prever têm de concordar."""
    p_cal, y_cal = dados_calibrados(3000, 12)
    p32 = p_cal.astype(np.float32)
    spec = conformal.calibrar(p32, y_cal, CLASSES, 0.10, "lac")
    assert (conformal.conjunto_de_predicao(p32, spec) == conformal.conjunto_de_predicao(p32.astype(float), spec)).all()
    cobre = conformal.avaliar(p32, y_cal, spec)["cobertura"]
    assert cobre >= 0.90  # na própria calibração a cobertura nunca fica abaixo do nível


def test_rotulos_fora_da_ordem_das_colunas():
    """As colunas seguem model.classes_; o rótulo 'verdadeiro' é mapeado por posição."""
    proba = np.array([[0.1, 0.8, 0.1], [0.7, 0.2, 0.1]] * 100)
    y = np.array([20, 10] * 100)
    spec = conformal.calibrar(proba, y, [10, 20, 30], 0.10, "lac")
    assert spec["classes"] == [10, 20, 30]
    assert conformal.avaliar(proba, y, spec)["cobertura"] == pytest.approx(1.0)


# --- escolha automática do método (só com dados de calibração) -----------------------------------

def test_escolha_automatica_usa_lac_quando_as_classes_sao_parecidas():
    p, y = dados_calibrados(8000, 13, concentracao=(1.0, 1.0, 1.0))
    assert conformal.escolher_metodo(p, y, CLASSES, 0.10, minimo=0.80) == "lac"


def test_escolha_automatica_usa_mondrian_quando_uma_classe_fica_mal_coberta():
    rng = np.random.default_rng(14)
    n = 8000
    y = rng.choice(3, size=n, p=[0.55, 0.20, 0.25])
    logits = rng.normal(0, 1, (n, 3))
    logits[np.arange(n), y] += np.where(y == 1, 1.0, 3.0)
    p = np.exp(logits) / np.exp(logits).sum(axis=1, keepdims=True)
    assert conformal.escolher_metodo(p, y, CLASSES, 0.10, minimo=0.85) == "mondrian"


def test_comparar_devolve_os_tres_metodos_com_as_colunas_do_relatorio():
    p_cal, y_cal = dados_calibrados(3000, 15)
    p_te, y_te = dados_calibrados(3000, 16)
    tabela = conformal.comparar(p_cal, y_cal, p_te, y_te, CLASSES, 0.10)
    assert list(tabela["metodo"]) == ["lac", "mondrian", "aps"]
    for coluna in ["q_hat", "cobertura_teste", "tamanho_medio_teste", "pct_tamanho_1_teste", "pct_tamanho_2_teste",
                   "pct_tamanho_3_teste", "cobertura_classe_0_teste", "cobertura_classe_2_teste",
                   "cobertura_calibracao", "cobertura_classe_1_calibracao"]:
        assert coluna in tabela.columns
    assert ((tabela[["pct_tamanho_1_teste", "pct_tamanho_2_teste", "pct_tamanho_3_teste"]].sum(axis=1) - 1).abs() < 1e-9).all()
