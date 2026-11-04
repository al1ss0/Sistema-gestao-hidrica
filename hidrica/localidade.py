"""Localidade da propriedade: município (geocodificação), coordenadas e altitude.

A localização é sempre escolhida pelo agricultor; a posição de quem acessa o sistema nunca é usada.
Geocodificação e altitude vêm da API pública do Open-Meteo (dados do GeoNames).
"""
import json
import math
import re
import unicodedata
import urllib.parse
import urllib.request
from dataclasses import dataclass

import config

URL_GEOCODIFICACAO = "https://geocoding-api.open-meteo.com/v1/search"
URL_ALTITUDE = "https://api.open-meteo.com/v1/elevation"
CABECALHOS = {"User-Agent": "HidroDecisao/1.0 (projeto academico)"}

FONTE_ALT_REFERENCIA = "referência do projeto"
FONTE_ALT_MUNICIPIO = "Open-Meteo (modelo digital de elevação)"
FONTE_ALT_USUARIO = "informada pelo usuário"
FONTE_ALT_NASA = "NASA POWER (altitude média da célula da grade)"


@dataclass(frozen=True)
class Localidade:
    nome: str
    lat: float
    lon: float
    alt: float | None  # None = ainda não conhecida; a NASA POWER informa a da célula da grade
    fonte_alt: str
    tipo: str          # referencia | municipio | coordenadas


REFERENCIA = Localidade(config.LOCAL_NOME, config.LAT, config.LON, config.ALT, FONTE_ALT_REFERENCIA, "referencia")


def normalizar(texto):
    sem_acento = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", sem_acento).strip().lower()


_UF_POR_NOME = {normalizar(nome): sigla for sigla, nome in config.UFS.items()}


def distancia_km(lat1, lon1, lat2, lon2):
    """Distância em km entre dois pontos (fórmula de haversine)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = (math.sin((p2 - p1) / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2)
    return 2 * 6371.0 * math.asin(math.sqrt(a))


def motivos_extrapolacao(local, analise):
    """Razões pelas quais o resultado do modelo seria extrapolação. Lista vazia = dentro do domínio."""
    motivos = []
    d = distancia_km(local.lat, local.lon, config.LAT, config.LON)
    if d > config.RAIO_DOMINIO_KM:
        motivos.append(
            f"a localidade fica a {d:.0f} km de {config.LOCAL_NOME}, o único ponto de clima usado no treino"
        )
    if analise.month not in config.MESES_ANALISE_TREINO:
        motivos.append("a data da análise está fora de outubro–maio, período coberto pelas safras simuladas do treino")
    return motivos


def _get_json(url, params, timeout):
    consulta = urllib.parse.urlencode(params)
    req = urllib.request.Request(f"{url}?{consulta}", headers=CABECALHOS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


def _uf_de(estado):
    return _UF_POR_NOME.get(normalizar(estado))


def buscar_municipios(texto, uf=None, timeout=10):
    """Municípios brasileiros cujo nome corresponde a `texto` (a coordenada é a da sede do município)."""
    texto = (texto or "").strip()
    if len(texto) < 3:
        return []
    dados = _get_json(
        URL_GEOCODIFICACAO,
        {"name": texto, "count": 50, "language": "pt", "format": "json", "countryCode": "BR"},
        timeout,
    )
    vistos, resultados = set(), []
    for r in dados.get("results") or []:
        if not str(r.get("feature_code", "")).startswith("PPL"):  # só localidades povoadas
            continue
        sigla = _uf_de(r.get("admin1"))
        if sigla is None or (uf and sigla != uf):
            continue
        chave = (normalizar(r["name"]), sigla)
        if chave in vistos:
            continue
        vistos.add(chave)
        resultados.append({"nome": r["name"], "uf": sigla, "lat": r["latitude"], "lon": r["longitude"],
                           "alt": r.get("elevation")})
    exatos = [x for x in resultados if normalizar(x["nome"]) == normalizar(texto)]
    return exatos or resultados


def altitude_de(lat, lon, timeout=10):
    """Altitude (m) do ponto, ou None se o serviço não responder."""
    try:
        dados = _get_json(URL_ALTITUDE, {"latitude": f"{lat:.5f}", "longitude": f"{lon:.5f}"}, timeout)
        return float(dados["elevation"][0])
    except Exception:
        return None


def _numero(texto):
    return float(str(texto).strip().replace(",", "."))


def _extrair_uf(texto, uf_campo):
    """Separa 'Sorriso – MT' em ('Sorriso', 'MT'). O sufixo do texto vale mais que o campo de estado."""
    m = re.match(r"^(.*?)\s*[–-]\s*([A-Za-z]{2})\s*$", texto)
    if m and m.group(2).upper() in config.UFS:
        return m.group(1).strip(), m.group(2).upper()
    return texto.strip(), (uf_campo.upper() if uf_campo and uf_campo.upper() in config.UFS else None)


def _resolver_municipio(form):
    texto = (form.get("municipio") or "").strip()
    if len(texto) < 3:
        return None, ["Informe o nome do município (pelo menos 3 letras) ou escolha informar as coordenadas."]
    if len(texto) > 80:
        return None, ["O nome do município é longo demais."]
    nome, uf = _extrair_uf(texto, (form.get("uf") or "").strip())
    try:
        achados = buscar_municipios(nome, uf)
    except Exception:
        return None, ["Não foi possível buscar o município agora. Tente de novo em instantes ou informe as coordenadas."]
    if not achados:
        onde = f" em {uf}" if uf else ""
        return None, [f"Município “{nome}”{onde} não encontrado. Confira o nome e o estado, ou informe as coordenadas."]
    if len(achados) > 1:
        opcoes = ", ".join(f"{a['nome']} – {a['uf']}" for a in achados[:8])
        return None, [f"Há mais de um resultado para “{nome}”: {opcoes}. Escolha o estado para continuar."]
    a = achados[0]
    alt = a["alt"]
    if alt is None:
        alt = altitude_de(a["lat"], a["lon"])
    return Localidade(f"{a['nome']} – {a['uf']}", float(a["lat"]), float(a["lon"]),
                      float(alt) if alt is not None else None,
                      FONTE_ALT_MUNICIPIO if alt is not None else FONTE_ALT_NASA, "municipio"), []


def _resolver_coordenadas(form):
    erros = []
    try:
        lat, lon = _numero(form.get("latitude")), _numero(form.get("longitude"))
    except (ValueError, TypeError):
        return None, ["Informe latitude e longitude em graus decimais, por exemplo -12,55 e -55,72."]
    if not (math.isfinite(lat) and math.isfinite(lon)):
        return None, ["Latitude e longitude devem ser números válidos."]
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None, ["Coordenadas fora do intervalo válido (latitude de −90 a 90, longitude de −180 a 180)."]
    if not (config.BRASIL_LAT[0] <= lat <= config.BRASIL_LAT[1] and config.BRASIL_LON[0] <= lon <= config.BRASIL_LON[1]):
        return None, ["As coordenadas estão fora do Brasil. Este protótipo atende propriedades brasileiras."]
    alt_txt = (form.get("altitude") or "").strip()
    if alt_txt:
        try:
            alt = _numero(alt_txt)
        except ValueError:
            return None, ["A altitude deve ser um número em metros."]
        if not (-100 <= alt <= 4000):
            return None, ["A altitude deve estar entre −100 e 4000 m."]
        fonte = FONTE_ALT_USUARIO
    else:
        alt = altitude_de(lat, lon)
        fonte = FONTE_ALT_MUNICIPIO if alt is not None else FONTE_ALT_NASA
    nome = f"Coordenadas {lat:.4f}, {lon:.4f}".replace(".", ",")
    return Localidade(nome, lat, lon, alt, fonte, "coordenadas"), erros


def resolver(form):
    """Interpreta a escolha de localidade do formulário. Retorna (Localidade, erros)."""
    modo = (form.get("local_modo") or "referencia").strip()
    if modo == "referencia":
        return REFERENCIA, []
    if modo == "municipio":
        return _resolver_municipio(form)
    if modo == "coordenadas":
        return _resolver_coordenadas(form)
    return None, ["Escolha como informar a localização da propriedade."]
