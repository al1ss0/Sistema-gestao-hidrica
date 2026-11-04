"""Fluxos de seleção de localidade, domínio do modelo, segurança e produção no app Flask."""
import pandas as pd
import pytest

import config
from app import MSG_FONTE_INDISPONIVEL, MSG_SEM_MODELO, create_app
from hidrica import clima as mod_clima
from hidrica import localidade as mod_local

HOJE = "2026-01-01"  # o clima sintético dos testes termina em 30/06/2025
SORRISO = {"nome": "Sorriso", "uf": "MT", "lat": -12.545, "lon": -55.711, "alt": 363.0}
ANALISE = {"cultura": "soja", "solo": "médio", "data_semeadura": "2024-10-10", "data_analise": "2025-01-20"}
RESULTADO = "Resultado da análise"


@pytest.fixture
def ambiente(clima, modelo_treinado, monkeypatch):
    """App com Open-Meteo e NASA substituídos por versões locais (nenhum teste usa a internet)."""
    monkeypatch.setattr(mod_local, "buscar_municipios",
                        lambda texto, uf=None, timeout=10: [SORRISO] if texto.strip().lower() == "sorriso" else [])
    monkeypatch.setattr(mod_local, "altitude_de", lambda lat, lon, timeout=10: 371.0)
    chamadas = []

    def janela(local, inicio, fim, timeout=60):
        chamadas.append((local, pd.Timestamp(inicio), pd.Timestamp(fim)))
        altitude = local.alt if local.alt is not None else 365.0
        return clima.loc[pd.Timestamp(inicio):pd.Timestamp(fim)].copy(), altitude

    monkeypatch.setattr(mod_clima, "obter_janela", janela)
    pasta = modelo_treinado[0]

    def criar(**kw):
        kw.setdefault("limite_por_minuto", 0)
        return create_app(pasta, clima=kw.pop("clima", clima), atualizar=False, hoje=HOJE, **kw).test_client()

    criar.chamadas = chamadas
    criar.pasta = pasta
    return criar


def test_formulario_tem_os_tres_modos_de_localizacao(ambiente):
    html = ambiente().get("/analise").get_data(as_text=True)
    assert "Localização da propriedade" in html
    for valor in ["referencia", "municipio", "coordenadas"]:
        assert f'name="local_modo" value="{valor}"' in html
    assert 'name="municipio"' in html and 'name="uf"' in html and 'id="lista-municipios"' in html
    assert 'name="latitude"' in html and 'name="longitude"' in html and 'name="altitude"' in html
    assert "não usa a localização de quem está acessando" in html
    assert 'value="referencia" checked' in html  # padrão


def test_link_de_exemplo_preenche_o_modo_municipio(ambiente):
    html = ambiente().get("/analise?local_modo=municipio&municipio=Sorriso – MT&cultura=soja").get_data(as_text=True)
    assert 'value="municipio" checked' in html and 'value="Sorriso – MT"' in html


def test_analise_de_outro_municipio_usa_o_clima_da_localidade(ambiente):
    c = ambiente()
    html = c.post("/analise", data={**ANALISE, "local_modo": "municipio", "municipio": "Sorriso"}).get_data(as_text=True)
    assert RESULTADO in html and "Sorriso – MT" in html and "(sede do município)" in html
    local, inicio, fim = ambiente.chamadas[-1]
    assert (local.lat, local.lon, local.alt) == (-12.545, -55.711, 363.0)
    assert (inicio, fim) == (pd.Timestamp("2024-10-10"), pd.Timestamp("2025-01-20"))  # só o período necessário
    assert "NASA POWER (série diária, grade de cerca de 50 km), consultada para esta localidade" in html
    assert "Distância do local de treino" in html


def test_outra_regiao_destaca_o_calculo_de_referencia_e_avisa_da_extrapolacao(ambiente):
    html = ambiente().post("/analise", data={**ANALISE, "local_modo": "municipio", "municipio": "Sorriso"}).get_data(as_text=True)
    assert "Consulta fora do domínio do modelo" in html
    assert "km de Passo Fundo – RS" in html
    assert "cálculo de referência FAO-56" in html
    assert "Estimativa do modelo (extrapolação)" in html


def test_local_de_referencia_dentro_da_epoca_destaca_o_modelo(ambiente):
    html = ambiente().post("/analise", data=ANALISE).get_data(as_text=True)
    assert RESULTADO in html
    assert "Consulta fora do domínio" not in html
    assert "modelo " in html and "Probabilidade atribuída pelo modelo" in html


def test_data_fora_da_epoca_de_treino_tambem_e_extrapolacao(ambiente):
    dados = {**ANALISE, "data_semeadura": "2024-06-10", "data_analise": "2024-07-20"}
    html = ambiente().post("/analise", data=dados).get_data(as_text=True)
    assert "Consulta fora do domínio do modelo" in html and "outubro–maio" in html


def test_analise_por_coordenadas(ambiente):
    dados = {**ANALISE, "local_modo": "coordenadas", "latitude": "-12,55", "longitude": "-55,72"}
    html = ambiente().post("/analise", data=dados).get_data(as_text=True)
    assert RESULTADO in html and "Coordenadas -12,5500, -55,7200" in html
    assert "371 m (Open-Meteo (modelo digital de elevação))" in html


def test_coordenadas_sem_altitude_do_servico_usam_a_da_grade(ambiente, monkeypatch):
    monkeypatch.setattr(mod_local, "altitude_de", lambda *a, **k: None)
    dados = {**ANALISE, "local_modo": "coordenadas", "latitude": "-12.55", "longitude": "-55.72"}
    html = ambiente().post("/analise", data=dados).get_data(as_text=True)
    assert "365 m (NASA POWER (altitude média da célula da grade))" in html


@pytest.mark.parametrize("dados, trecho", [
    ({"latitude": "40.7", "longitude": "-74"}, "fora do Brasil"),
    ({"latitude": "abc", "longitude": "-74"}, "graus decimais"),
    ({"latitude": "-12", "longitude": "-55", "altitude": "x"}, "altitude deve ser um número"),
])
def test_coordenadas_invalidas_mostram_erro_sem_buscar_clima(ambiente, dados, trecho):
    html = ambiente().post("/analise", data={**ANALISE, "local_modo": "coordenadas", **dados}).get_data(as_text=True)
    assert trecho in html and RESULTADO not in html and ambiente.chamadas == []


def test_municipio_inexistente(ambiente):
    html = ambiente().post("/analise", data={**ANALISE, "local_modo": "municipio", "municipio": "Lugar Nenhum"}).get_data(as_text=True)
    assert "não encontrado" in html and RESULTADO not in html and ambiente.chamadas == []


def test_municipio_homonimo_pede_o_estado(ambiente, monkeypatch):
    achados = [{**SORRISO, "nome": "Santa Rosa", "uf": "RS"}, {**SORRISO, "nome": "Santa Rosa", "uf": "MT"}]
    monkeypatch.setattr(mod_local, "buscar_municipios", lambda *a, **k: achados)
    html = ambiente().post("/analise", data={**ANALISE, "local_modo": "municipio", "municipio": "Santa Rosa"}).get_data(as_text=True)
    assert "Santa Rosa – RS" in html and "Santa Rosa – MT" in html and RESULTADO not in html


def test_erros_de_localidade_e_de_datas_aparecem_juntos(ambiente):
    dados = {"cultura": "soja", "solo": "médio", "local_modo": "municipio", "municipio": "Lugar Nenhum"}
    html = ambiente().post("/analise", data=dados).get_data(as_text=True)
    assert "não encontrado" in html and "Informe a data de semeadura" in html


def test_fonte_de_clima_indisponivel(ambiente, monkeypatch):
    def falha(*a, **k):
        raise OSError("sem rede")

    monkeypatch.setattr(mod_clima, "obter_janela", falha)
    html = ambiente().post("/analise", data={**ANALISE, "local_modo": "municipio", "municipio": "Sorriso"}).get_data(as_text=True)
    assert MSG_FONTE_INDISPONIVEL in html and RESULTADO not in html


def test_localidade_sem_dados_ate_a_data_pedida(ambiente, clima, monkeypatch):
    def curta(local, inicio, fim, timeout=60):
        return clima.loc[pd.Timestamp(inicio):pd.Timestamp("2025-01-10")].copy(), 363.0

    monkeypatch.setattr(mod_clima, "obter_janela", curta)
    html = ambiente().post("/analise", data={**ANALISE, "local_modo": "municipio", "municipio": "Sorriso"}).get_data(as_text=True)
    assert "vão até 10/01/2025" in html and RESULTADO not in html


def test_data_futura_e_recusada_mesmo_sem_clima_salvo(ambiente, monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(mod_clima, "ultima_data_completa", lambda *a, **k: pd.Timestamp("2025-12-28"))
    c = create_app(ambiente.pasta, atualizar=False, hoje=HOJE, limite_por_minuto=0).test_client()
    dados = {**ANALISE, "data_semeadura": "2025-12-01", "data_analise": "2026-02-01"}
    assert "não pode ser posterior à data atual" in c.post("/analise", data=dados).get_data(as_text=True)


def test_funciona_sem_arquivo_de_clima_buscando_sob_demanda(ambiente, monkeypatch, tmp_path):
    """Situação da hospedagem: não há data/clima.csv, tudo vem da NASA POWER na hora."""
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(mod_clima, "ultima_data_completa", lambda *a, **k: pd.Timestamp("2025-06-28"))
    c = create_app(ambiente.pasta, atualizar=False, hoje=HOJE, limite_por_minuto=0).test_client()
    pagina = c.get("/analise").get_data(as_text=True)
    assert 'max="2025-06-28"' in pagina and 'value="2025-06-28"' in pagina
    assert "Atualizar dados climáticos de referência agora" not in pagina  # nada salvo para atualizar
    html = c.post("/analise", data=ANALISE).get_data(as_text=True)
    assert RESULTADO in html
    assert ambiente.chamadas[-1][0].tipo == "referencia"
    assert "Clima obtido sob demanda" in c.get("/").get_data(as_text=True)


def test_sem_modelo_a_pagina_avisa(ambiente, tmp_path, clima):
    c = create_app(tmp_path, clima=clima, atualizar=False, hoje=HOJE).test_client()
    assert MSG_SEM_MODELO in c.get("/analise").get_data(as_text=True)
    assert c.get("/saude").get_json() == {"status": "ok", "modelo": False}


# --- API de sugestão de municípios ---------------------------------------------------------------

def test_api_municipios_devolve_rotulos(ambiente):
    resposta = ambiente().get("/api/municipios?q=Sorriso")
    assert resposta.status_code == 200
    assert resposta.get_json() == [{"rotulo": "Sorriso – MT", "nome": "Sorriso", "uf": "MT"}]


def test_api_municipios_busca_curta_ou_desconhecida_devolve_lista_vazia(ambiente):
    c = ambiente()
    assert c.get("/api/municipios?q=So").get_json() == []
    assert c.get("/api/municipios?q=Nenhum").get_json() == []


def test_api_municipios_com_servico_fora_do_ar(ambiente, monkeypatch):
    def falha(*a, **k):
        raise OSError("fora")

    monkeypatch.setattr(mod_local, "buscar_municipios", falha)
    assert ambiente().get("/api/municipios?q=Sorriso").status_code == 502


# --- segurança e produção ------------------------------------------------------------------------

def test_cabecalhos_de_seguranca(ambiente):
    h = ambiente().get("/").headers
    assert "default-src 'self'" in h["Content-Security-Policy"] and "frame-ancestors 'none'" in h["Content-Security-Policy"]
    assert h["X-Frame-Options"] == "DENY" and h["X-Content-Type-Options"] == "nosniff"
    assert "Referrer-Policy" in h


def test_politica_de_seguranca_nao_exige_scripts_inline(ambiente):
    html = ambiente().get("/analise").get_data(as_text=True)
    assert "<script>" not in html and "onclick=" not in html  # só scripts externos e JSON


def test_saude(ambiente):
    resposta = ambiente().get("/saude")
    assert resposta.status_code == 200 and resposta.get_json() == {"status": "ok", "modelo": True}


def test_pagina_inexistente(ambiente):
    resposta = ambiente().get("/nao-existe")
    assert resposta.status_code == 404 and "Página não encontrada" in resposta.get_data(as_text=True)


def test_texto_digitado_nao_e_executado_na_pagina(ambiente):
    ataque = '"><script>alert(1)</script>'
    html = ambiente().post("/analise", data={**ANALISE, "local_modo": "municipio", "municipio": ataque}).get_data(as_text=True)
    assert "<script>alert(1)</script>" not in html and "&lt;script&gt;" in html


def test_limite_de_consultas_por_minuto(ambiente):
    c = ambiente(limite_por_minuto=3)
    for _ in range(3):
        assert c.get("/api/municipios?q=Sorriso").status_code == 200
    bloqueada = c.get("/api/municipios?q=Sorriso")
    assert bloqueada.status_code == 429 and "Muitas consultas" in bloqueada.get_json()["erro"]
    assert c.get("/analise").status_code == 200  # páginas comuns não contam no limite
    pagina = c.post("/analise", data=ANALISE)  # o POST compartilha o mesmo limite
    assert pagina.status_code == 429 and "Muitas consultas" in pagina.get_data(as_text=True)


def test_limite_e_por_endereco(ambiente):
    c = ambiente(limite_por_minuto=1)
    assert c.get("/api/municipios?q=Sorriso", environ_overrides={"REMOTE_ADDR": "10.0.0.1"}).status_code == 200
    assert c.get("/api/municipios?q=Sorriso", environ_overrides={"REMOTE_ADDR": "10.0.0.1"}).status_code == 429
    assert c.get("/api/municipios?q=Sorriso", environ_overrides={"REMOTE_ADDR": "10.0.0.2"}).status_code == 200


def test_atras_de_proxy_o_ip_vem_do_cabecalho(ambiente, monkeypatch):
    monkeypatch.setenv("HIDRO_PROXY", "1")
    c = ambiente(limite_por_minuto=1)
    cab = lambda ip: {"X-Forwarded-For": ip}  # noqa: E731
    assert c.get("/api/municipios?q=Sorriso", headers=cab("1.1.1.1")).status_code == 200
    assert c.get("/api/municipios?q=Sorriso", headers=cab("2.2.2.2")).status_code == 200
    assert c.get("/api/municipios?q=Sorriso", headers=cab("1.1.1.1")).status_code == 429


def test_sem_proxy_o_cabecalho_e_ignorado(ambiente, monkeypatch):
    monkeypatch.delenv("HIDRO_PROXY", raising=False)
    c = ambiente(limite_por_minuto=1)
    cab = lambda ip: {"X-Forwarded-For": ip}  # noqa: E731
    assert c.get("/api/municipios?q=Sorriso", headers=cab("1.1.1.1")).status_code == 200
    assert c.get("/api/municipios?q=Sorriso", headers=cab("2.2.2.2")).status_code == 429  # não dá para burlar


def test_variaveis_de_ambiente_configuram_o_limite(ambiente, monkeypatch):
    monkeypatch.setenv("HIDRO_LIMITE_POR_MIN", "1")
    c = create_app(ambiente.pasta, clima=None, atualizar=False, hoje=HOJE).test_client()
    assert c.get("/api/municipios?q=Sorriso").status_code == 200
    assert c.get("/api/municipios?q=Sorriso").status_code == 429


def test_wsgi_expoe_a_aplicacao(monkeypatch):
    monkeypatch.setenv("HIDRO_ATUALIZAR", "0")
    import importlib

    import wsgi
    importlib.reload(wsgi)
    assert wsgi.app.test_client().get("/saude").status_code == 200
