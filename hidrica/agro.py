"""Cálculos agronômicos FAO-56 (spec.md, seção 6)."""
import numpy as np

import config


def et0(tmax, tmin, ur, vento, rad, lat, alt, doy):
    """ET0 diária de Penman-Monteith (mm/dia). Aceita números, arrays ou Series."""
    tmax = np.asarray(tmax, dtype=float)
    tmin = np.asarray(tmin, dtype=float)
    ur = np.asarray(ur, dtype=float)
    vento = np.asarray(vento, dtype=float)
    rad = np.asarray(rad, dtype=float)
    doy = np.asarray(doy, dtype=float)

    t = (tmax + tmin) / 2
    pressao = 101.3 * ((293 - 0.0065 * alt) / 293) ** 5.26
    gama = 0.000665 * pressao

    def e0(x):
        return 0.6108 * np.exp(17.27 * x / (x + 237.3))

    delta = 4098 * e0(t) / (t + 237.3) ** 2
    es = (e0(tmax) + e0(tmin)) / 2
    ea = ur / 100 * es

    phi = np.radians(lat)
    dr = 1 + 0.033 * np.cos(2 * np.pi * doy / 365)
    decl = 0.409 * np.sin(2 * np.pi * doy / 365 - 1.39)
    ws = np.arccos(np.clip(-np.tan(phi) * np.tan(decl), -1, 1))
    ra = (24 * 60 / np.pi) * 0.0820 * dr * (
        ws * np.sin(phi) * np.sin(decl) + np.cos(phi) * np.cos(decl) * np.sin(ws)
    )
    rso = (0.75 + 2e-5 * alt) * ra
    rnl = (
        4.903e-9
        * ((tmax + 273.16) ** 4 + (tmin + 273.16) ** 4)
        / 2
        * (0.34 - 0.14 * np.sqrt(ea))
        * (1.35 * np.minimum(rad / rso, 1.0) - 0.35)
    )
    rn = 0.77 * rad - rnl
    return (0.408 * delta * rn + gama * (900 / (t + 273)) * vento * (es - ea)) / (
        delta + gama * (1 + 0.34 * vento)
    )


def duracao_ciclo(cultura):
    return int(sum(config.CULTURAS[cultura]["estagios"]))


def kc(cultura, d):
    """Kc no dia d após a semeadura (d começa em 0)."""
    c = config.CULTURAS[cultura]
    ini, dev, mid, late = c["estagios"]
    if d < ini:
        return c["kc_ini"]
    if d < ini + dev:
        return c["kc_ini"] + (d - ini) / dev * (c["kc_mid"] - c["kc_ini"])
    if d < ini + dev + mid:
        return c["kc_mid"]
    frac = min((d - ini - dev - mid) / late, 1.0)
    return c["kc_mid"] + frac * (c["kc_end"] - c["kc_mid"])


def taw(cultura, solo):
    s = config.SOLOS[solo]
    return 1000 * (s["fc"] - s["wp"]) * config.CULTURAS[cultura]["zr"]


def raw(cultura, solo):
    return config.CULTURAS[cultura]["p"] * taw(cultura, solo)


def classificar(dr, raw_mm, alpha=config.ALPHA):
    if dr >= raw_mm:
        return 2
    if dr >= alpha * raw_mm:
        return 1
    return 0
