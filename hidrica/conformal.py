"""Predição conformal (split) para o classificador de 3 classes.

Em vez de uma única classe, devolve um *conjunto* de classes que contém a classe verdadeira em
pelo menos 1 − α dos casos (cobertura marginal), desde que os dados novos sejam "parecidos" com
os de calibração (trocáveis). É o equivalente do intervalo de predição para classificação.

Implementado à mão com numpy (sem MAPIE): o algoritmo é curto, não traz dependência nova e fica
testável. O modelo NÃO pode ter sido ajustado com os dados de calibração; senão as probabilidades
na calibração ficam otimistas, o limiar fica baixo demais e os conjuntos viram sempre de 1 classe.

Métodos (todos com o mesmo procedimento: calcular o score de não conformidade na calibração, tomar
o quantil q̂ de nível ceil((n+1)(1−α))/n e montar o conjunto de cada caso novo):
- lac:      score = 1 − p(classe verdadeira). Conjuntos menores; garantia marginal.
- mondrian: o mesmo, com um q̂ por classe verdadeira. Garantia de cobertura por classe.
- aps:      score = soma das probabilidades até a classe verdadeira (ordem decrescente). Mais adaptativo
            e conservador. Versão sem aleatorização, para o resultado ser determinístico.
"""
import math

import numpy as np
import pandas as pd

import config

METODOS = ("lac", "mondrian", "aps")


def _validar_alfa(alfa):
    if not 0 < alfa < 1:
        raise ValueError("alfa deve estar entre 0 e 1 (exclusive).")


def quantil_conforme(scores, alfa):
    """q̂ = a k-ésima menor pontuação, com k = ceil((n+1)(1−α)) (correção de amostra finita).

    Se n for pequeno demais (k > n), devolve 1.0, que inclui todas as classes.
    """
    _validar_alfa(alfa)
    scores = np.asarray(scores, dtype=float)
    n = len(scores)
    if n == 0:
        return 1.0
    k = math.ceil(round((n + 1) * (1 - alfa), 9))  # o round evita que 9.000000000000002 vire 10
    if k > n:
        return 1.0
    return float(np.sort(scores)[k - 1])


def indices_das_classes(y, classes):
    """Posição (coluna de predict_proba) de cada rótulo verdadeiro."""
    mapa = {c: i for i, c in enumerate(classes)}
    return np.array([mapa[c] for c in np.asarray(y)], dtype=int)


def _proba(proba):
    return np.atleast_2d(np.asarray(proba, dtype=float))


def scores_lac(proba, idx):
    proba = _proba(proba)
    return 1.0 - proba[np.arange(len(proba)), idx]


def _acumulado_ordenado(proba):
    ordem = np.argsort(-proba, axis=1, kind="stable")
    return ordem, np.cumsum(np.take_along_axis(proba, ordem, axis=1), axis=1)


def scores_aps(proba, idx):
    proba = _proba(proba)
    ordem, acum = _acumulado_ordenado(proba)
    posicao = np.argmax(ordem == idx[:, None], axis=1)
    return acum[np.arange(len(proba)), posicao]


def calibrar(proba_cal, y_cal, classes, alfa=config.CONFORMAL_ALFA, metodo="lac"):
    """Calibra e devolve a especificação (dicionário simples, que vai no metadata.json do modelo)."""
    _validar_alfa(alfa)
    if metodo not in METODOS:
        raise ValueError(f"método desconhecido: {metodo!r}")
    proba = _proba(proba_cal)
    idx = indices_das_classes(y_cal, classes)
    if metodo == "aps":
        q = quantil_conforme(scores_aps(proba, idx), alfa)
    else:
        s = scores_lac(proba, idx)
        q = quantil_conforme(s, alfa) if metodo == "lac" else [
            quantil_conforme(s[idx == k], alfa) for k in range(len(classes))
        ]
    return {
        "metodo": metodo, "alfa": alfa, "nivel": round(1 - alfa, 6), "q_hat": q,
        "classes": [int(c) for c in classes], "n_calibracao": int(len(idx)),
    }


def conjunto_de_predicao(proba, spec):
    """Matriz booleana (n, K): True onde a classe está no conjunto. Nunca fica vazio.

    Sempre inclui a classe mais provável, o que só pode aumentar a cobertura (nunca reduzi-la).
    """
    proba = _proba(proba)
    metodo = spec["metodo"]
    if metodo == "lac":
        mascara = (1.0 - proba) <= float(spec["q_hat"])
    elif metodo == "mondrian":
        mascara = (1.0 - proba) <= np.asarray(spec["q_hat"], dtype=float)[None, :]
    elif metodo == "aps":
        ordem, acum = _acumulado_ordenado(proba)
        mascara = np.zeros(proba.shape, dtype=bool)
        np.put_along_axis(mascara, ordem, acum <= float(spec["q_hat"]), axis=1)
    else:
        raise ValueError(f"método desconhecido: {metodo!r}")
    mascara[np.arange(len(proba)), proba.argmax(axis=1)] = True
    return mascara


def avaliar(proba, y, spec):
    """Cobertura, tamanho dos conjuntos e cobertura por classe em um conjunto de dados."""
    classes = spec["classes"]
    mascara = conjunto_de_predicao(proba, spec)
    idx = indices_das_classes(y, classes)
    cobre = mascara[np.arange(len(idx)), idx]
    tamanho = mascara.sum(axis=1)
    return {
        "n": int(len(idx)),
        "cobertura": float(cobre.mean()),
        "tamanho_medio": float(tamanho.mean()),
        "distribuicao_tamanhos": {str(k): float((tamanho == k).mean()) for k in range(1, len(classes) + 1)},
        "cobertura_por_classe": {
            str(int(c)): (float(cobre[idx == i].mean()) if (idx == i).any() else None) for i, c in enumerate(classes)
        },
    }


def escolher_metodo(proba_cal, y_cal, classes, alfa=config.CONFORMAL_ALFA,
                    minimo=config.CONFORMAL_COBERTURA_MINIMA_CLASSE):
    """Regra do modo "auto", decidida só com dados de calibração (sem olhar o teste).

    Usa o LAC global; se, na própria calibração, alguma classe ficar abaixo de `minimo`, usa Mondrian.
    """
    spec = calibrar(proba_cal, y_cal, classes, alfa, "lac")
    por_classe = [v for v in avaliar(proba_cal, y_cal, spec)["cobertura_por_classe"].values() if v is not None]
    return "mondrian" if por_classe and min(por_classe) < minimo else "lac"


def _texto_q(q):
    return ";".join(f"{x:.4f}" for x in q) if isinstance(q, list) else f"{q:.4f}"


def comparar(proba_cal, y_cal, proba_te, y_te, classes, alfa=config.CONFORMAL_ALFA):
    """Tabela com os três métodos: calibração em proba_cal/y_cal, avaliação em proba_te/y_te."""
    linhas = []
    for metodo in METODOS:
        spec = calibrar(proba_cal, y_cal, classes, alfa, metodo)
        teste = avaliar(proba_te, y_te, spec)
        cal = avaliar(proba_cal, y_cal, spec)  # em amostra: serve para decidir o método sem olhar o teste
        linha = {
            "metodo": metodo, "nivel": spec["nivel"], "q_hat": _texto_q(spec["q_hat"]),
            "n_calibracao": spec["n_calibracao"], "n_teste": teste["n"],
            "cobertura_teste": teste["cobertura"], "tamanho_medio_teste": teste["tamanho_medio"],
        }
        linha.update({f"pct_tamanho_{k}_teste": v for k, v in teste["distribuicao_tamanhos"].items()})
        linha.update({f"cobertura_classe_{c}_teste": v for c, v in teste["cobertura_por_classe"].items()})
        linha["cobertura_calibracao"] = cal["cobertura"]
        linha.update({f"cobertura_classe_{c}_calibracao": v for c, v in cal["cobertura_por_classe"].items()})
        linhas.append(linha)
    return pd.DataFrame(linhas)
