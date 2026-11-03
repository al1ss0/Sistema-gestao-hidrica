"""Validação do formulário e geração da recomendação (spec.md, seção 9)."""
import base64
import io

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

import config  # noqa: E402
from hidrica import agro, dataset  # noqa: E402


def _data(texto):
    texto = (texto or "").strip()
    if not texto:
        return None
    try:
        return pd.Timestamp(texto)
    except (ValueError, TypeError):
        return False


def validar(form, clima):
    """Retorna (entrada, erros). Se houver erros, entrada é None."""
    erros = []
    cultura = (form.get("cultura") or "").strip()
    solo = (form.get("solo") or "").strip()
    if cultura not in config.CULTURAS:
        erros.append("Selecione uma cultura válida.")
    if solo not in config.SOLOS:
        erros.append("Selecione um tipo de solo válido.")

    semeadura = _data(form.get("data_semeadura"))
    analise = _data(form.get("data_analise"))
    irr_data = _data(form.get("data_irrigacao"))
    if semeadura is None:
        erros.append("Informe a data de semeadura.")
    elif semeadura is False:
        erros.append("A data de semeadura é inválida.")
    if analise is None:
        erros.append("Informe a data da análise.")
    elif analise is False:
        erros.append("A data da análise é inválida.")
    if irr_data is False:
        erros.append("A data da última irrigação é inválida.")

    lamina_txt = (form.get("lamina_irrigacao") or "").strip().replace(",", ".")
    lamina = None
    if lamina_txt:
        try:
            lamina = float(lamina_txt)
        except ValueError:
            erros.append("A lâmina da última irrigação deve ser um número (mm).")
    if irr_data and lamina is None and "A lâmina da última irrigação deve ser um número (mm)." not in erros:
        erros.append("Informe a lâmina da última irrigação (mm).")
    if lamina is not None and lamina <= 0:
        erros.append("A lâmina da última irrigação deve ser maior que 0.")
    if lamina is not None and not irr_data:
        erros.append("Informe a data da última irrigação.")

    datas_ok = isinstance(semeadura, pd.Timestamp) and isinstance(analise, pd.Timestamp)
    if datas_ok:
        if analise <= semeadura:
            erros.append("A data da análise deve ser posterior à semeadura.")
        elif cultura in config.CULTURAS:
            ultimo = semeadura + pd.Timedelta(days=agro.duracao_ciclo(cultura) - 1)
            if analise > ultimo:
                erros.append(
                    f"A data da análise passa do fim do ciclo da cultura ({ultimo.date().isoformat()})."
                )
        inicio, fim = clima.index.min(), clima.index.max()
        if semeadura < inicio or analise > fim:
            erros.append(
                f"As datas devem estar entre {inicio.date().isoformat()} e {fim.date().isoformat()}, "
                "período dos dados climáticos."
            )
        if isinstance(irr_data, pd.Timestamp) and not (semeadura <= irr_data <= analise):
            erros.append("A data da última irrigação deve estar entre a semeadura e a data da análise.")

    if erros:
        return None, erros
    entrada = {
        "cultura": cultura,
        "solo": solo,
        "semeadura": semeadura,
        "analise": analise,
        "irrigacao_data": irr_data if isinstance(irr_data, pd.Timestamp) else None,
        "lamina": lamina,
    }
    return entrada, []


def _grafico(sim):
    ultimos = sim.tail(30)
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(8, 6), sharex=True)
    ax1.bar(ultimos["data"], ultimos["chuva"], color="#4a90d9", label="Chuva (mm)")
    ax1.bar(ultimos["data"], ultimos["irrigacao"], color="#2e7d32", label="Irrigação (mm)")
    ax1.plot(ultimos["data"], ultimos["etc"], color="#d9534f", marker="o", markersize=3, label="ETc (mm/dia)")
    ax1.set_ylabel("mm/dia")
    ax1.set_title("Últimos 30 dias")
    ax1.legend(loc="upper left", fontsize=8)
    ax2.plot(ultimos["data"], ultimos["dr"], color="#8d6e63", marker="o", markersize=3, label="Déficit hídrico Dr (mm)")
    ax2.axhline(ultimos["raw"].iloc[-1], color="#d9534f", linestyle="--", label="RAW (limite de estresse)")
    ax2.set_ylabel("mm")
    ax2.legend(loc="upper left", fontsize=8)
    fig.autofmt_xdate()
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=100)
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def recomendar(entrada, clima, modelo, metadata):
    irrigacoes = {}
    if entrada["irrigacao_data"] is not None:
        irrigacoes[entrada["irrigacao_data"]] = entrada["lamina"]
    sim = dataset.simular_cenario(
        clima, entrada["cultura"], entrada["solo"], entrada["semeadura"], "manual",
        irrigacoes=irrigacoes, data_fim=entrada["analise"],
    )
    sim = dataset.adicionar_features(sim)
    linha = sim.iloc[[-1]]
    proba = modelo.predict_proba(linha[metadata["features"]])[0]
    classes = [int(c) for c in modelo.classes_]
    classe_modelo = classes[int(proba.argmax())]
    classe_ref = int(linha["classe"].iloc[0])
    dr = float(linha["dr"].iloc[0])
    raw = float(linha["raw"].iloc[0])
    return {
        "classe_modelo": classe_modelo,
        "texto_modelo": config.NOMES_CLASSES[classe_modelo],
        "probabilidades": {config.NOMES_CLASSES[c]: round(float(p) * 100, 1) for c, p in zip(classes, proba)},
        "classe_referencia": classe_ref,
        "texto_referencia": config.NOMES_CLASSES[classe_ref],
        "divergente": classe_modelo != classe_ref,
        "dr": round(dr, 1),
        "raw": round(raw, 1),
        "lamina": round(dr, 1) if classe_modelo >= 1 else None,
        "grafico": _grafico(sim),
        "aviso": config.AVISO,
    }
