"""Treino, comparação e seleção de modelos (spec.md, seção 8)."""
import json
from datetime import datetime
from pathlib import Path

import joblib
import pandas as pd
from sklearn.base import clone
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import balanced_accuracy_score, f1_score, recall_score
from sklearn.model_selection import GridSearchCV, GroupKFold, train_test_split
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from xgboost import XGBClassifier

import config
from hidrica import dataset

# Ordem de preferência no desempate: do modelo mais simples ao mais complexo.
MODELOS = {
    "RegressaoLogistica": (
        lambda: LogisticRegression(max_iter=1000, random_state=config.SEED),
        {"C": [0.1, 1, 10], "class_weight": [None, "balanced"]},
    ),
    "RandomForest": (
        lambda: RandomForestClassifier(n_jobs=-1, random_state=config.SEED),
        {"n_estimators": [100], "max_depth": [10, None], "class_weight": [None, "balanced"]},
    ),
    "XGBoost": (
        lambda: XGBClassifier(tree_method="hist", subsample=0.8, n_jobs=-1, random_state=config.SEED),
        {"n_estimators": [200], "max_depth": [4, 6], "learning_rate": [0.1]},
    ),
    "MLP": (
        lambda: MLPClassifier(early_stopping=True, max_iter=300, random_state=config.SEED),
        {"hidden_layer_sizes": [(32,), (64, 32)], "alpha": [0.0001, 0.001]},
    ),
}
TOLERANCIA_EMPATE = 0.01


def criar_pipeline(estimador):
    pre = ColumnTransformer([
        ("cat", OneHotEncoder(handle_unknown="ignore"), dataset.CATEGORICAS),
        ("num", StandardScaler(), dataset.NUMERICAS),
    ])
    return Pipeline([("pre", pre), ("modelo", estimador)])


def _metricas(pipe, df):
    pred = pipe.predict(df[dataset.FEATURES])
    y = df["classe"]
    return {
        "f1_macro": f1_score(y, pred, average="macro"),
        "acuracia_balanceada": balanced_accuracy_score(y, pred),
        "recall_classe2": recall_score(y, pred, labels=[2], average=None, zero_division=0)[0],
    }


def _json_seguro(obj):
    if hasattr(obj, "item"):
        return obj.item()
    if isinstance(obj, tuple):
        return list(obj)
    return str(obj)


def treinar_e_avaliar(df, pasta_saida=config.RAIZ, rapido=False):
    pasta_saida = Path(pasta_saida)
    treino, validacao, teste = dataset.dividir(df)
    if rapido:
        treino, _ = train_test_split(
            treino, train_size=3000, stratify=treino["classe"], random_state=config.SEED
        )

    ajustados = {}
    melhores_params = {}
    for nome, (fabrica, grade) in MODELOS.items():
        if rapido:
            grade = {k: v[:1] for k, v in grade.items()}
        grade = {f"modelo__{k}": v for k, v in grade.items()}
        busca = GridSearchCV(
            criar_pipeline(fabrica()), grade, scoring="f1_macro", cv=GroupKFold(n_splits=3)
        )
        busca.fit(treino[dataset.FEATURES], treino["classe"], groups=treino["ano"])
        ajustados[nome] = busca.best_estimator_
        melhores_params[nome] = {k.removeprefix("modelo__"): v for k, v in busca.best_params_.items()}
    dummy = criar_pipeline(DummyClassifier(strategy="most_frequent"))
    dummy.fit(treino[dataset.FEATURES], treino["classe"])

    val = {nome: _metricas(p, validacao) for nome, p in ajustados.items()}
    val["Dummy"] = _metricas(dummy, validacao)

    melhor_f1 = max(val[nome]["f1_macro"] for nome in MODELOS)
    vencedor = next(
        nome for nome in MODELOS if val[nome]["f1_macro"] >= melhor_f1 - TOLERANCIA_EMPATE
    )

    final = clone(ajustados[vencedor])
    treino_val = pd.concat([treino, validacao])
    final.fit(treino_val[dataset.FEATURES], treino_val["classe"])

    tst = {nome: _metricas(p, teste) for nome, p in ajustados.items()}
    tst["Dummy"] = _metricas(dummy, teste)
    tst[vencedor] = _metricas(final, teste)

    linhas = []
    for nome in list(MODELOS) + ["Dummy"]:
        linhas.append({
            "modelo": nome,
            **{f"{k}_validacao": v for k, v in val[nome].items()},
            **{f"{k}_teste": v for k, v in tst[nome].items()},
            "selecionado": nome == vencedor,
        })
    metricas = pd.DataFrame(linhas)

    (pasta_saida / "reports").mkdir(parents=True, exist_ok=True)
    (pasta_saida / "models").mkdir(parents=True, exist_ok=True)
    metricas.round(4).to_csv(pasta_saida / "reports" / "metricas.csv", index=False)
    texto = (
        f"Modelo selecionado: {vencedor}\n"
        f"F1-macro na validação: {val[vencedor]['f1_macro']:.4f}\n"
        f"Critério: maior F1-macro na validação; empate (diferença < {TOLERANCIA_EMPATE}) "
        "resolvido pelo modelo mais simples.\n"
        "Métricas de teste do modelo selecionado: retreinado em treino + validação e avaliado uma vez.\n"
        "Métricas de teste dos demais modelos: ajustados só no treino (apenas para a tabela).\n"
        "Limitação: os rótulos vêm do balanço hídrico FAO-56; as métricas medem concordância "
        "com a simulação, não validade agronômica.\n"
    )
    (pasta_saida / "reports" / "selecao.txt").write_text(texto, encoding="utf-8")

    joblib.dump(final, pasta_saida / "models" / "modelo.joblib")
    metadata = {
        "modelo": vencedor,
        "hiperparametros": melhores_params[vencedor],
        "features": dataset.FEATURES,
        "metricas": {"validacao": val[vencedor], "teste": tst[vencedor]},
        "data": datetime.now().isoformat(timespec="seconds"),
    }
    (pasta_saida / "models" / "metadata.json").write_text(
        json.dumps(metadata, indent=2, default=_json_seguro, ensure_ascii=False), encoding="utf-8"
    )
    return {"metricas": metricas, "vencedor": vencedor, "metadata": metadata}


def carregar_modelo(pasta=config.RAIZ):
    pasta = Path(pasta)
    pipe = joblib.load(pasta / "models" / "modelo.joblib")
    metadata = json.loads((pasta / "models" / "metadata.json").read_text(encoding="utf-8"))
    return pipe, metadata
