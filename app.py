"""Interface Flask. Local: python app.py. Produção: gunicorn wsgi:app (ver DEPLOY.md)."""
import os
import threading
import time
from collections import defaultdict, deque
from dataclasses import replace
from datetime import date, datetime
from pathlib import Path

import pandas as pd
from flask import Flask, jsonify, redirect, render_template, request, url_for

import config
from hidrica import agro
from hidrica import clima as mod_clima
from hidrica import localidade as mod_local
from hidrica import modelo as mod_modelo
from hidrica import recomendacao

MSG_SEM_MODELO = "Modelo não encontrado. Execute: python pipeline.py"
MSG_FONTE_INDISPONIVEL = (
    "Não foi possível obter os dados climáticos desta localidade agora (fonte indisponível). "
    "Tente novamente em instantes."
)
MSGS_ATUALIZACAO = {
    "ok": ("sucesso", "Dados climáticos de referência atualizados com a NASA POWER."),
    "falha": ("erro", "Não foi possível atualizar os dados agora (sem conexão ou fonte indisponível). "
                      "Os dados já salvos continuam em uso."),
}

# Exemplos que apenas preenchem o formulário; o resultado é calculado normalmente.
PRESETS_HISTORICOS = [
    {"titulo": "Milho em solo médio", "rotulo": "Safra 2024/25", "local_rotulo": config.LOCAL_NOME,
     "cultura": "milho", "solo": "médio", "data_semeadura": "2024-10-15", "data_analise": "2025-01-10"},
    {"titulo": "Soja em solo argiloso", "rotulo": "Safra 2024/25, com irrigação informada", "local_rotulo": config.LOCAL_NOME,
     "cultura": "soja", "solo": "argiloso", "data_semeadura": "2024-11-01", "data_analise": "2025-01-20",
     "data_irrigacao": "2025-01-12", "lamina_irrigacao": "25"},
    {"titulo": "Feijão em solo arenoso", "rotulo": "Safra 2024/25", "local_rotulo": config.LOCAL_NOME,
     "cultura": "feijão", "solo": "arenoso", "data_semeadura": "2024-10-15", "data_analise": "2025-01-05"},
]
PRESET_OUTRA_REGIAO = {
    "titulo": "Soja em solo médio", "rotulo": "Safra 2025/26, outra região", "local_rotulo": "Sorriso – MT",
    "local_modo": "municipio", "municipio": "Sorriso – MT",
    "cultura": "soja", "solo": "médio", "data_semeadura": "2025-10-10", "data_analise": "2026-01-20",
}


def _br(ts):
    return pd.Timestamp(ts).strftime("%d/%m/%Y")


class LimitadorTaxa:
    """Limite simples de requisições por IP em janela de 1 minuto (em memória; protege as APIs externas)."""

    def __init__(self, limite_por_minuto):
        self.limite = limite_por_minuto
        self._registros = defaultdict(deque)
        self._trava = threading.Lock()

    def permitir(self, chave):
        if not self.limite:
            return True
        agora = time.monotonic()
        with self._trava:
            fila = self._registros[chave]
            while fila and agora - fila[0] > 60:
                fila.popleft()
            if len(fila) >= self.limite:
                return False
            fila.append(agora)
            if len(self._registros) > 5000:  # evita crescer sem limite sob ataque
                for k in [k for k, v in self._registros.items() if not v or agora - v[-1] > 60][:2500]:
                    del self._registros[k]
            return True


CSP = ("default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; "
       "connect-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'self'")


def create_app(pasta=config.RAIZ, clima=None, atualizar=None, hoje=None, limite_por_minuto=None):
    """`hoje` fixa a data atual (testes). `atualizar=False` não consulta a internet na inicialização.

    Variáveis de ambiente: HIDRO_ATUALIZAR (0 desliga a atualização automática), HIDRO_LIMITE_POR_MIN
    (requisições por minuto por IP; 0 desliga) e HIDRO_PROXY (1 quando há proxy reverso, como nas
    hospedagens, para ler o IP real do visitante).
    """
    pasta = Path(pasta)
    app = Flask(__name__)
    if os.environ.get("HIDRO_PROXY") == "1":
        from werkzeug.middleware.proxy_fix import ProxyFix
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
    if atualizar is None:
        atualizar = os.environ.get("HIDRO_ATUALIZAR", "1") != "0"
    if limite_por_minuto is None:
        limite_por_minuto = int(os.environ.get("HIDRO_LIMITE_POR_MIN", "30"))
    limitador = LimitadorTaxa(limite_por_minuto)
    agora = (lambda: pd.Timestamp(hoje)) if hoje is not None else (lambda: pd.Timestamp(date.today()))

    # Clima do local de referência salvo em disco (opcional: sem ele, tudo é obtido sob demanda).
    estado = {"clima": clima, "meta": None, "aviso": None}
    if clima is None:
        try:
            estado["clima"] = mod_clima.carregar_clima()
            estado["meta"] = mod_clima.carregar_meta()
        except FileNotFoundError:
            pass

    def desatualizado():
        meta = estado["meta"]
        if estado["clima"] is None or not meta:
            return False  # sem arquivo salvo não há o que atualizar: o clima é buscado sob demanda
        return datetime.fromisoformat(meta["atualizado_em"]).date() < agora().date()

    def atualizar_dados(timeout):
        try:
            mod_clima.atualizar_clima(hoje=agora(), timeout=timeout)
            estado["clima"] = mod_clima.carregar_clima()
            estado["meta"] = mod_clima.carregar_meta()
            estado["aviso"] = None
            return True
        except Exception as erro:  # sem internet, fonte fora do ar, resposta inesperada
            estado["aviso"] = f"Não foi possível atualizar o clima ({erro}). Usando os dados já salvos."
            return False

    if clima is None and atualizar and desatualizado():
        atualizar_dados(timeout=30)

    try:
        pipe, metadata = mod_modelo.carregar_modelo(pasta)
    except FileNotFoundError:
        pipe, metadata = None, None
    metricas = None
    arquivo_metricas = pasta / "reports" / "metricas.csv"
    if arquivo_metricas.exists():
        metricas = pd.read_csv(arquivo_metricas)
    tabela_conformal = None
    arquivo_conformal = pasta / "reports" / "conformal.csv"
    if arquivo_conformal.exists():
        tabela_conformal = pd.read_csv(arquivo_conformal)

    def ultima_data_referencia():
        """Último dia completo de clima do local de referência (arquivo salvo ou consulta à fonte)."""
        if estado["clima"] is not None:
            return estado["clima"].index.max()
        try:
            return mod_clima.ultima_data_completa(mod_local.REFERENCIA, agora())
        except Exception:
            return None

    def status_clima():
        df = estado["clima"]
        if df is None:
            return None
        meta = estado["meta"] or {}
        atualizado = meta.get("atualizado_em")
        return {
            "primeira_data": _br(df.index.min()),
            "ultima_data": _br(df.index.max()),
            "defasagem_dias": max((agora().normalize() - df.index.max()).days, 0),
            "atualizado_em": datetime.fromisoformat(atualizado).strftime("%d/%m/%Y %H:%M") if atualizado else None,
            "fonte_nome": meta.get("fonte_nome", "Fonte não informada"),
            "tipo_dado": meta.get("tipo_dado", ""),
            "aviso": estado["aviso"],
        }

    @app.before_request
    def controlar_taxa():
        consulta_externa = (
            (request.path == "/analise" and request.method == "POST")
            or request.path in ("/api/municipios", "/atualizar-dados")
        )
        if consulta_externa and not limitador.permitir(request.remote_addr or "?"):
            if request.path.startswith("/api/"):
                return jsonify({"erro": "Muitas consultas. Aguarde um minuto."}), 429
            return render_template("erro.html", pagina="", titulo_erro="Muitas consultas",
                                   mensagem="Você fez muitas consultas em pouco tempo. Aguarde cerca de um minuto "
                                            "e tente de novo."), 429

    @app.after_request
    def cabecalhos_de_seguranca(resposta):
        resposta.headers.setdefault("Content-Security-Policy", CSP)
        resposta.headers.setdefault("X-Content-Type-Options", "nosniff")
        resposta.headers.setdefault("X-Frame-Options", "DENY")
        resposta.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        return resposta

    @app.context_processor
    def contexto_global():
        return {"status_clima": status_clima(), "local_nome": config.LOCAL_NOME, "ano": agora().year}

    def _presets():
        lista = [dict(p) for p in PRESETS_HISTORICOS]
        df = estado["clima"]
        if df is not None:
            _, ultima = recomendacao.limites_datas(df, agora())
            semeadura = ultima - pd.Timedelta(days=40)
            if semeadura >= df.index.min():
                lista.append({
                    "titulo": "Milho em solo médio", "rotulo": "Situação atual, com os dados mais recentes",
                    "local_rotulo": config.LOCAL_NOME, "cultura": "milho", "solo": "médio",
                    "data_semeadura": semeadura.date().isoformat(), "data_analise": ultima.date().isoformat(),
                })
        lista.append(dict(PRESET_OUTRA_REGIAO))
        for p in lista:
            p["consulta"] = {k: v for k, v in p.items() if k not in ("titulo", "rotulo", "local_rotulo")}
        return lista

    @app.route("/")
    def inicio():
        return render_template("inicio.html", presets=_presets(), pagina="inicio")

    @app.route("/saude")
    def saude():
        return jsonify({"status": "ok", "modelo": pipe is not None})

    @app.route("/api/municipios")
    def api_municipios():
        uf = (request.args.get("uf") or "").upper() or None
        try:
            achados = mod_local.buscar_municipios(request.args.get("q", ""), uf if uf in config.UFS else None)
        except Exception:
            return jsonify({"erro": "Busca indisponível no momento."}), 502
        return jsonify([{"rotulo": f"{a['nome']} – {a['uf']}", "nome": a["nome"], "uf": a["uf"]} for a in achados[:10]])

    def _obter_clima(local, entrada, erros):
        """Clima da localidade para o período da análise. Acrescenta a `erros` se não for possível."""
        usa_salvo = local.tipo == "referencia" and estado["clima"] is not None
        if usa_salvo:
            return estado["clima"], local
        try:
            df, altitude = mod_clima.obter_janela(local, entrada["semeadura"], entrada["analise"])
        except Exception:
            erros.append(MSG_FONTE_INDISPONIVEL)
            return None, local
        if local.alt is None:
            local = replace(local, alt=altitude, fonte_alt=mod_local.FONTE_ALT_NASA)
        problema = mod_clima.verificar_cobertura(df, entrada["semeadura"], entrada["analise"])
        if problema:
            erros.append(problema)
            return None, local
        return df, local

    @app.route("/analise", methods=["GET", "POST"])
    def analise():
        form = request.form if request.method == "POST" else request.args
        erros, res, local = [], None, None
        disponivel = pipe is not None
        if request.method == "POST" and disponivel:
            local, erros_local = mod_local.resolver(form)
            erros.extend(erros_local)
            df_ref = estado["clima"]
            if local is not None and local.tipo == "referencia" and df_ref is not None:
                limites_clima = df_ref
            else:  # outra localidade: aceita datas até hoje e confere a cobertura depois de buscar o clima
                limites_clima = pd.DataFrame(index=pd.date_range(config.DATA_INICIO, agora()))
            entrada, erros_form = recomendacao.validar(form, limites_clima, agora())  # erros de local e de datas juntos
            erros.extend(erros_form)
            if local is not None and entrada is not None and not erros:
                df, local = _obter_clima(local, entrada, erros)
                if df is not None:
                    res = recomendacao.recomendar(entrada, df, pipe, metadata, local)
        ultima_ref = ultima_data_referencia()
        primeira = pd.Timestamp(config.DATA_INICIO)
        ultimo_dia = min(ultima_ref, agora()) if ultima_ref is not None else agora()
        msg = MSGS_ATUALIZACAO.get(request.args.get("msg"))
        return render_template(
            "analise.html", pagina="analise", form=form, erros=erros, res=res,
            aviso_modelo=None if disponivel else MSG_SEM_MODELO,
            data_min=primeira.date().isoformat(), data_max=ultimo_dia.date().isoformat(),
            modelo_nome=metadata["modelo"] if metadata else None,
            culturas={n: {**c, "ciclo": agro.duracao_ciclo(n)} for n, c in config.CULTURAS.items()},
            solos=config.SOLOS, ufs=config.UFS, metricas=metricas, msg_atualizacao=msg, presets=_presets(),
            permite_atualizar=estado["clima"] is not None,
        )

    @app.route("/atualizar-dados", methods=["POST"])
    def atualizar_rota():
        ok = atualizar_dados(timeout=60) if estado["clima"] is not None else False
        return redirect(url_for("analise", msg="ok" if ok else "falha") + "#plataforma")

    @app.route("/metodologia")
    def metodologia():
        return render_template(
            "metodologia.html", pagina="metodologia", metricas=metricas, metadata=metadata,
            conformal=metadata.get("conformal") if metadata else None, tabela_conformal=tabela_conformal,
            culturas={n: {**c, "ciclo": agro.duracao_ciclo(n)} for n, c in config.CULTURAS.items()},
            solos=config.SOLOS, alpha=config.ALPHA, nomes_classes=config.NOMES_CLASSES,
            anos_treino=(min(config.ANOS_TREINO), max(config.ANOS_TREINO)),
            anos_validacao=config.ANOS_VALIDACAO, anos_teste=config.ANOS_TESTE,
            raio_km=config.RAIO_DOMINIO_KM,
        )

    @app.route("/sobre")
    def sobre():
        return render_template("sobre.html", pagina="sobre")

    @app.errorhandler(404)
    def nao_encontrado(_):
        return render_template("erro.html", pagina="", titulo_erro="Página não encontrada",
                               mensagem="O endereço acessado não existe."), 404

    return app


if __name__ == "__main__":
    create_app().run(host="127.0.0.1", port=5000, debug=False)
