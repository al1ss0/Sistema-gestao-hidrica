import pandas as pd
import pytest

import config
from hidrica import localidade as loc


def _resultado(nome, uf_nome, lat, lon, alt=300.0, codigo="PPL"):
    return {"name": nome, "admin1": uf_nome, "latitude": lat, "longitude": lon, "elevation": alt,
            "feature_code": codigo, "country_code": "BR"}


RESPOSTA_SANTA_ROSA = {"results": [
    _resultado("Santa Rosa", "Rio Grande do Sul", -27.87, -54.48),
    _resultado("Nova Santa Rosa", "Paraná", -24.47, -53.95, codigo="PPLA2"),
    _resultado("Santa Rosa", "Mato Grosso", -8.92, -57.42),
    _resultado("Santa Rosa", "Piauí", -8.37, -43.85),
    _resultado("Santa Rosa Airport", "Mato Grosso", -8.9, -57.4, codigo="AIRP"),
]}
RESPOSTA_SORRISO = {"results": [
    _resultado("Sorriso", "Mato Grosso", -12.545, -55.711, alt=363.0),
    _resultado("Sorriso Airport", "Mato Grosso", -12.48, -55.67, codigo="AIRP"),
]}


@pytest.fixture
def geocodificador(monkeypatch):
    """Substitui a API do Open-Meteo: devolve a resposta configurada e guarda os parâmetros recebidos."""
    estado = {"resposta": RESPOSTA_SORRISO, "chamadas": []}

    def falso(url, params, timeout):
        estado["chamadas"].append((url, params))
        if estado["resposta"] is None:
            raise OSError("sem rede")
        return estado["resposta"]

    monkeypatch.setattr(loc, "_get_json", falso)
    return estado


def test_normalizar_remove_acentos_e_caixa():
    assert loc.normalizar("  São  PAULO ") == "sao paulo"


def test_distancia_conhecida():
    assert loc.distancia_km(config.LAT, config.LON, config.LAT, config.LON) == pytest.approx(0, abs=1e-6)
    # Passo Fundo (RS) a Sorriso (MT): da ordem de 1.700 km em linha reta.
    assert 1500 < loc.distancia_km(config.LAT, config.LON, -12.545, -55.711) < 1900


def test_busca_ignora_o_que_nao_e_localidade_povoada(geocodificador):
    achados = loc.buscar_municipios("Sorriso")
    assert [a["nome"] for a in achados] == ["Sorriso"]  # o aeroporto fica de fora
    assert achados[0]["uf"] == "MT" and achados[0]["alt"] == 363.0


def test_busca_pede_apenas_localidades_do_brasil(geocodificador):
    loc.buscar_municipios("Sorriso")
    params = geocodificador["chamadas"][0][1]
    assert params["countryCode"] == "BR" and params["name"] == "Sorriso"


def test_busca_com_menos_de_3_letras_nao_consulta(geocodificador):
    assert loc.buscar_municipios("So") == []
    assert geocodificador["chamadas"] == []


def test_busca_prefere_nome_exato_e_filtra_por_uf(geocodificador):
    geocodificador["resposta"] = RESPOSTA_SANTA_ROSA
    todos = loc.buscar_municipios("Santa Rosa")
    assert {(a["nome"], a["uf"]) for a in todos} == {("Santa Rosa", "RS"), ("Santa Rosa", "MT"), ("Santa Rosa", "PI")}
    so_mt = loc.buscar_municipios("Santa Rosa", "MT")
    assert [(a["nome"], a["uf"]) for a in so_mt] == [("Santa Rosa", "MT")]


def test_resolver_padrao_e_o_local_de_referencia():
    local, erros = loc.resolver({})
    assert erros == [] and local == loc.REFERENCIA and local.tipo == "referencia"


def test_resolver_municipio(geocodificador):
    local, erros = loc.resolver({"local_modo": "municipio", "municipio": "Sorriso"})
    assert erros == []
    assert (local.nome, local.tipo) == ("Sorriso – MT", "municipio")
    assert local.alt == 363.0 and local.fonte_alt == loc.FONTE_ALT_MUNICIPIO


def test_resolver_municipio_com_sufixo_de_estado(geocodificador):
    geocodificador["resposta"] = RESPOSTA_SANTA_ROSA
    local, erros = loc.resolver({"local_modo": "municipio", "municipio": "Santa Rosa – MT"})
    assert erros == [] and local.nome == "Santa Rosa – MT"


def test_resolver_municipio_homonimo_pede_o_estado(geocodificador):
    geocodificador["resposta"] = RESPOSTA_SANTA_ROSA
    local, erros = loc.resolver({"local_modo": "municipio", "municipio": "Santa Rosa"})
    assert local is None
    assert "mais de um resultado" in erros[0] and "Santa Rosa – MT" in erros[0] and "Santa Rosa – RS" in erros[0]


def test_resolver_municipio_com_estado_do_campo(geocodificador):
    geocodificador["resposta"] = RESPOSTA_SANTA_ROSA
    local, erros = loc.resolver({"local_modo": "municipio", "municipio": "Santa Rosa", "uf": "RS"})
    assert erros == [] and local.nome == "Santa Rosa – RS"


def test_resolver_municipio_inexistente(geocodificador):
    geocodificador["resposta"] = {"results": []}
    local, erros = loc.resolver({"local_modo": "municipio", "municipio": "Cidadezinha Inventada"})
    assert local is None and "não encontrado" in erros[0]


def test_resolver_municipio_servico_fora_do_ar(geocodificador):
    geocodificador["resposta"] = None
    local, erros = loc.resolver({"local_modo": "municipio", "municipio": "Sorriso"})
    assert local is None and "Não foi possível buscar o município" in erros[0]


@pytest.mark.parametrize("texto", ["", "ab", "x" * 81])
def test_resolver_municipio_texto_invalido(geocodificador, texto):
    local, erros = loc.resolver({"local_modo": "municipio", "municipio": texto})
    assert local is None and erros and geocodificador["chamadas"] == []


def test_resolver_coordenadas_com_virgula_decimal(monkeypatch):
    monkeypatch.setattr(loc, "altitude_de", lambda lat, lon, timeout=10: 371.0)
    local, erros = loc.resolver({"local_modo": "coordenadas", "latitude": "-12,55", "longitude": "-55,72"})
    assert erros == []
    assert (local.lat, local.lon, local.alt, local.tipo) == (-12.55, -55.72, 371.0, "coordenadas")
    assert local.fonte_alt == loc.FONTE_ALT_MUNICIPIO and "-12,5500" in local.nome


def test_resolver_coordenadas_altitude_informada_vale_mais_que_a_busca(monkeypatch):
    monkeypatch.setattr(loc, "altitude_de", lambda *a, **k: pytest.fail("não deveria consultar a altitude"))
    local, _ = loc.resolver({"local_modo": "coordenadas", "latitude": "-12.55", "longitude": "-55.72", "altitude": "400"})
    assert local.alt == 400.0 and local.fonte_alt == loc.FONTE_ALT_USUARIO


def test_resolver_coordenadas_sem_altitude_disponivel_deixa_para_a_nasa(monkeypatch):
    monkeypatch.setattr(loc, "altitude_de", lambda *a, **k: None)
    local, erros = loc.resolver({"local_modo": "coordenadas", "latitude": "-12.55", "longitude": "-55.72"})
    assert erros == [] and local.alt is None and local.fonte_alt == loc.FONTE_ALT_NASA


@pytest.mark.parametrize("dados, trecho", [
    ({"latitude": "abc", "longitude": "-55"}, "graus decimais"),
    ({"latitude": "", "longitude": ""}, "graus decimais"),
    ({"latitude": "95", "longitude": "-55"}, "fora do intervalo"),
    ({"latitude": "-12", "longitude": "200"}, "fora do intervalo"),
    ({"latitude": "40.7", "longitude": "-74.0"}, "fora do Brasil"),
    ({"latitude": "nan", "longitude": "-55"}, "números válidos"),
    ({"latitude": "-12", "longitude": "-55", "altitude": "muito alto"}, "altitude deve ser um número"),
    ({"latitude": "-12", "longitude": "-55", "altitude": "99999"}, "entre −100 e 4000"),
])
def test_resolver_coordenadas_invalidas(monkeypatch, dados, trecho):
    monkeypatch.setattr(loc, "altitude_de", lambda *a, **k: 100.0)
    local, erros = loc.resolver({"local_modo": "coordenadas", **dados})
    assert local is None and any(trecho in e for e in erros)


def test_modo_desconhecido_e_recusado():
    local, erros = loc.resolver({"local_modo": "gps_do_visitante"})
    assert local is None and erros


def test_altitude_de_devolve_none_se_a_rede_falha(monkeypatch):
    def falha(*a, **k):
        raise OSError("sem rede")

    monkeypatch.setattr(loc, "_get_json", falha)
    assert loc.altitude_de(-12.5, -55.7) is None


def test_motivos_de_extrapolacao():
    sorriso = loc.Localidade("Sorriso – MT", -12.545, -55.711, 363, "x", "municipio")
    janeiro, julho = pd.Timestamp("2026-01-15"), pd.Timestamp("2026-07-15")
    assert loc.motivos_extrapolacao(loc.REFERENCIA, janeiro) == []
    assert any("km de" in m for m in loc.motivos_extrapolacao(sorriso, janeiro))
    assert any("outubro–maio" in m for m in loc.motivos_extrapolacao(loc.REFERENCIA, julho))
    assert len(loc.motivos_extrapolacao(sorriso, julho)) == 2
    perto = loc.Localidade("Perto", config.LAT + 0.2, config.LON, 600, "x", "coordenadas")  # ~22 km
    assert loc.motivos_extrapolacao(perto, janeiro) == []
