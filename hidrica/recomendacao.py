"""Validação do formulário e geração da recomendação (spec.md, seção 9)."""
import base64
import io
from datetime import date

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402  (sem pyplot: seguro com várias requisições simultâneas)

import config  # noqa: E402
from hidrica import agro, dataset, localidade  # noqa: E402

# Cores dos gráficos (paleta categórica validada: slots 1 a 3) e tintas neutras.
COR_CHUVA = "#2a78d6"
COR_ETC = "#eb6834"
COR_IRRIGACAO = "#1baf7a"
TINTA = "#1f2933"
TINTA_SUAVE = "#52606d"
GRADE = "#e4e7eb"


def _br(ts):
    return pd.Timestamp(ts).strftime("%d/%m/%Y")


def _data(texto):
    texto = (texto or "").strip()
    if not texto:
        return None
    try:
        return pd.Timestamp(texto)
    except (ValueError, TypeError):
        return False


def limites_datas(clima, hoje=None):
    """Primeira e última data aceitas para a análise: a última é limitada pela fonte e pela data atual."""
    hoje = pd.Timestamp(hoje if hoje is not None else date.today()).normalize()
    return clima.index.min(), min(clima.index.max(), hoje)


def validar(form, clima, hoje=None):
    """Retorna (entrada, erros). Se houver erros, entrada é None.

    Não há data máxima fixa: o limite superior é o último dia completo do clima carregado,
    sem passar da data atual.
    """
    hoje = pd.Timestamp(hoje if hoje is not None else date.today()).normalize()
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
    lamina_invalida = False
    if lamina_txt:
        try:
            lamina = float(lamina_txt)
        except ValueError:
            lamina_invalida = True
            erros.append("A lâmina da última irrigação deve ser um número (mm).")
    if irr_data and lamina is None and not lamina_invalida:
        erros.append("Informe a lâmina da última irrigação (mm).")
    if lamina is not None and lamina <= 0:
        erros.append("A lâmina da última irrigação deve ser maior que 0.")
    if lamina is not None and not irr_data:
        erros.append("Informe a data da última irrigação.")

    if isinstance(semeadura, pd.Timestamp) and isinstance(analise, pd.Timestamp):
        primeira, ultima = clima.index.min(), clima.index.max()
        if analise <= semeadura:
            erros.append("A data da análise deve ser posterior à semeadura.")
        elif cultura in config.CULTURAS:
            fim_ciclo = semeadura + pd.Timedelta(days=agro.duracao_ciclo(cultura) - 1)
            if analise > fim_ciclo:
                erros.append(
                    f"A data da análise passa do fim do ciclo da cultura ({_br(fim_ciclo)}). "
                    "Escolha uma data dentro do ciclo."
                )
        if analise > hoje:
            erros.append(f"A data da análise não pode ser posterior à data atual ({_br(hoje)}).")
        elif analise > ultima:
            erros.append(
                f"Os dados climáticos disponíveis vão até {_br(ultima)}: a fonte tem alguns dias de "
                "defasagem. Escolha uma data até lá ou use \"Atualizar dados climáticos\"."
            )
        if semeadura < primeira:
            erros.append(f"A data de semeadura não pode ser anterior ao início dos dados climáticos ({_br(primeira)}).")
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


def _estilizar(ax):
    for lado in ("top", "right"):
        ax.spines[lado].set_visible(False)
    for lado in ("left", "bottom"):
        ax.spines[lado].set_color(GRADE)
    ax.grid(axis="y", color=GRADE, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.tick_params(colors=TINTA_SUAVE, labelsize=8, length=0)
    ax.yaxis.label.set_color(TINTA_SUAVE)
    ax.yaxis.label.set_size(9)


def _png(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, facecolor="white", bbox_inches="tight", pad_inches=0.15)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _legenda(ax):
    """Legenda abaixo do gráfico, para não cobrir as linhas e barras."""
    leg = ax.legend(frameon=False, fontsize=8, loc="upper center", bbox_to_anchor=(0.5, -0.13), ncol=2)
    for texto in leg.get_texts():
        texto.set_color(TINTA)
    return leg


def _grafico_30_dias(sim):
    """Chuva, irrigação e ETc dos últimos 30 dias (mesma unidade, um único eixo)."""
    ult = sim.tail(30)
    fig = Figure(figsize=(8, 3.2))
    ax = fig.subplots()
    ax.bar(ult["data"], ult["chuva"], width=0.7, color=COR_CHUVA, label="Chuva (mm)")
    ax.bar(ult["data"], ult["irrigacao"], bottom=ult["chuva"], width=0.7, color=COR_IRRIGACAO,
           edgecolor="white", linewidth=1, label="Irrigação informada (mm)")
    ax.plot(ult["data"], ult["etc"], color=COR_ETC, linewidth=2, label="Evapotranspiração da cultura, ETc (mm/dia)")
    ax.set_ylabel("mm por dia")
    ax.xaxis.set_major_formatter(matplotlib.dates.DateFormatter("%d/%m"))
    _estilizar(ax)
    _legenda(ax)
    fig.tight_layout()
    return _png(fig)


def _grafico_ciclo(sim):
    """Déficit hídrico (Dr) desde a semeadura, com os limites RAW e TAW."""
    fig = Figure(figsize=(8, 3.4))
    ax = fig.subplots()
    raw, taw = float(sim["raw"].iloc[-1]), float(sim["taw"].iloc[-1])
    ax.plot(sim["data"], sim["dr"], color=COR_CHUVA, linewidth=2, label="Déficit hídrico, Dr (mm)")
    ax.axhline(raw, color=COR_ETC, linestyle="--", linewidth=1.4, label=f"RAW = {raw:.1f} mm (limite de estresse)")
    ax.axhline(taw, color=TINTA_SUAVE, linestyle=":", linewidth=1.4, label=f"TAW = {taw:.1f} mm (água disponível total)")
    irr = sim[sim["irrigacao"] > 0]
    if len(irr):
        ax.scatter(irr["data"], [0] * len(irr), marker="^", s=38, color=COR_IRRIGACAO,
                   edgecolor="white", linewidth=1, zorder=3, label="Irrigação informada")
    ax.set_ylim(-0.04 * taw, taw * 1.08)
    ax.set_ylabel("mm")
    ax.xaxis.set_major_formatter(matplotlib.dates.DateFormatter("%d/%m"))
    _estilizar(ax)
    _legenda(ax)
    fig.tight_layout()
    return _png(fig)


def _recomendacoes(classe, dr, raw, alerta, lamina, chuva_7d, etc_7d, divergente, texto_outro, origem):
    """Textos de manejo derivados só dos valores calculados. `classe` é a classe principal exibida."""
    itens = []
    if classe == 0:
        itens.append(
            f"Não há necessidade de irrigar na data analisada: o déficit hídrico (Dr = {dr:.1f} mm) está abaixo "
            f"do limite de alerta ({alerta:.1f} mm)."
        )
    elif classe == 1:
        itens.append(
            f"Planeje a irrigação: o déficit hídrico (Dr = {dr:.1f} mm) passou do limite de alerta "
            f"({alerta:.1f} mm), mas ainda não atingiu o limite de estresse (RAW = {raw:.1f} mm)."
        )
        itens.append(f"Lâmina líquida para repor o solo até a capacidade de campo: {lamina:.1f} mm.")
    else:
        itens.append(
            f"Irrigação recomendada: o déficit hídrico (Dr = {dr:.1f} mm) atingiu o limite de estresse "
            f"(RAW = {raw:.1f} mm), a partir do qual a cultura passa a sofrer restrição hídrica pelo método FAO-56."
        )
        itens.append(
            f"Lâmina líquida para repor o solo até a capacidade de campo: {lamina:.1f} mm. A lâmina bruta depende "
            "da eficiência do sistema de irrigação, que não é informada neste protótipo."
        )
    itens.append(
        f"Nos últimos 7 dias choveram {chuva_7d:.1f} mm e a cultura demandou {etc_7d:.1f} mm (ETc)."
    )
    if origem == "referência":
        itens.append(
            f"A estimativa do modelo de Machine Learning, que aqui é extrapolação, indica \"{texto_outro}\". "
            "Use-a apenas como informação complementar."
        )
    elif divergente:
        itens.append(
            f"O cálculo de referência (balanço hídrico) indica \"{texto_outro}\". Considere os dois resultados e "
            "consulte assistência técnica."
        )
    return itens


def recomendar(entrada, clima, modelo, metadata, local=None):
    """Análise de uma propriedade. `local` é a localidade escolhida (padrão: o local de referência).

    Se a consulta estiver fora do domínio de treino do modelo (localidade distante do ponto de treino ou
    data fora de outubro–maio), o resultado principal passa a ser o cálculo de referência FAO-56, que vale
    para qualquer localidade, e a classe do modelo é exibida como estimativa secundária.
    """
    local = local or localidade.REFERENCIA
    irrigacoes = {}
    if entrada["irrigacao_data"] is not None:
        irrigacoes[entrada["irrigacao_data"]] = entrada["lamina"]
    sim = dataset.simular_cenario(
        clima, entrada["cultura"], entrada["solo"], entrada["semeadura"], "manual",
        irrigacoes=irrigacoes, data_fim=entrada["analise"],
    )
    sim = dataset.adicionar_features(sim)
    linha = sim.iloc[[-1]]
    ultima = linha.iloc[0]
    proba = modelo.predict_proba(linha[metadata["features"]])[0]
    classes = [int(c) for c in modelo.classes_]
    classe_modelo = classes[int(proba.argmax())]
    classe_ref = int(ultima["classe"])
    motivos = localidade.motivos_extrapolacao(local, entrada["analise"])
    fora_do_dominio = bool(motivos)
    classe_principal = classe_ref if fora_do_dominio else classe_modelo
    origem = "referência" if fora_do_dominio else "modelo"
    dr, raw, taw = float(ultima["dr"]), float(ultima["raw"]), float(ultima["taw"])
    alerta = config.ALPHA * raw
    lamina = round(dr, 1) if classe_principal >= 1 else None
    divergente = classe_modelo != classe_ref
    dias = int(ultima["d"])
    sem_irrigacao = entrada["irrigacao_data"] is None
    texto_outro = config.NOMES_CLASSES[classe_modelo] if fora_do_dominio else config.NOMES_CLASSES[classe_ref]

    serie = [
        {"data": _br(r.data), "chuva": round(r.chuva, 1), "irrigacao": round(r.irrigacao, 1),
         "etc": round(r.etc, 2), "dr": round(r.dr, 1)}
        for r in sim.tail(30).itertuples()
    ]
    return {
        "classe_principal": classe_principal,
        "texto_principal": config.NOMES_CLASSES[classe_principal],
        "origem_principal": origem,
        "fora_do_dominio": fora_do_dominio,
        "motivos_extrapolacao": motivos,
        "local": {
            "nome": local.nome, "lat": local.lat, "lon": local.lon, "alt": local.alt,
            "fonte_alt": local.fonte_alt, "tipo": local.tipo,
            "distancia_km": round(localidade.distancia_km(local.lat, local.lon, config.LAT, config.LON)),
        },
        "classe_modelo": classe_modelo,
        "texto_modelo": config.NOMES_CLASSES[classe_modelo],
        "probabilidades": {config.NOMES_CLASSES[c]: round(float(p) * 100, 1) for c, p in zip(classes, proba)},
        "classe_referencia": classe_ref,
        "texto_referencia": config.NOMES_CLASSES[classe_ref],
        "divergente": divergente,
        "dr": round(dr, 1),
        "raw": round(raw, 1),
        "taw": round(taw, 1),
        "alerta": round(alerta, 1),
        "agua_disponivel": round(taw - dr, 1),
        "pct_esgotada": round(100 * dr / taw, 1),
        "pct_raw": round(100 * raw / taw, 1),
        "pct_alerta": round(100 * alerta / taw, 1),
        "lamina": lamina,
        "estagio": agro.estagio(entrada["cultura"], dias),
        "kc": round(float(ultima["kc"]), 2),
        "dias_apos_semeadura": dias,
        "clima": {
            "chuva_7d": round(float(ultima["chuva_7d"]), 1),
            "chuva_14d": round(float(ultima["chuva_14d"]), 1),
            "et0_7d": round(float(ultima["et0_7d"]), 1),
            "etc_7d": round(float(ultima["etc_7d"]), 1),
            "tmax_7d": round(float(ultima["tmax_7d"]), 1),
            "ur_7d": round(float(ultima["ur_7d"]), 0),
            "vento_7d": round(float(ultima["vento_7d"]), 1),
            "rad_7d": round(float(ultima["rad_7d"]), 1),
            "dias_desde_chuva": int(ultima["dias_desde_chuva"]),
            "dias_desde_irrigacao": None if sem_irrigacao else int(ultima["dias_desde_irrigacao"]),
        },
        "recomendacoes": _recomendacoes(
            classe_principal, dr, raw, alerta, round(dr, 1), float(ultima["chuva_7d"]), float(ultima["etc_7d"]),
            divergente, texto_outro, origem,
        ),
        "entrada": {
            "cultura": entrada["cultura"],
            "solo": entrada["solo"],
            "semeadura": _br(entrada["semeadura"]),
            "analise": _br(entrada["analise"]),
            "irrigacao_data": _br(entrada["irrigacao_data"]) if not sem_irrigacao else None,
            "lamina": entrada["lamina"],
        },
        "serie": serie,
        "grafico": _grafico_30_dias(sim),
        "grafico_ciclo": _grafico_ciclo(sim),
        "aviso": config.AVISO,
    }
