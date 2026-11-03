"""Interface Flask. Uso: python app.py (abre em http://127.0.0.1:5000)."""
from pathlib import Path

import pandas as pd
from flask import Flask, render_template, request

import config
from hidrica import clima as mod_clima
from hidrica import modelo as mod_modelo
from hidrica import recomendacao

MSG_SEM_MODELO = "Modelo não encontrado. Execute: python pipeline.py"


def create_app(pasta=config.RAIZ, clima=None):
    pasta = Path(pasta)
    app = Flask(__name__)

    if clima is None:
        try:
            clima = mod_clima.carregar_clima()
        except FileNotFoundError:
            clima = None
    try:
        pipe, metadata = mod_modelo.carregar_modelo(pasta)
    except FileNotFoundError:
        pipe, metadata = None, None
    disponivel = pipe is not None and clima is not None

    metricas = None
    arquivo_metricas = pasta / "reports" / "metricas.csv"
    if arquivo_metricas.exists():
        metricas = pd.read_csv(arquivo_metricas)

    @app.route("/", methods=["GET", "POST"])
    def index():
        contexto = {
            "culturas": list(config.CULTURAS),
            "solos": list(config.SOLOS),
            "form": request.form if request.method == "POST" else {},
            "erros": [],
            "res": None,
            "aviso_modelo": None if disponivel else MSG_SEM_MODELO,
            "metricas": metricas,
            "aviso": config.AVISO,
            "modelo_nome": metadata["modelo"] if metadata else None,
        }
        if request.method == "POST" and disponivel:
            entrada, erros = recomendacao.validar(request.form, clima)
            contexto["erros"] = erros
            if entrada is not None:
                contexto["res"] = recomendacao.recomendar(entrada, clima, pipe, metadata)
        return render_template("index.html", **contexto)

    return app


if __name__ == "__main__":
    create_app().run(host="127.0.0.1", port=5000, debug=False)
