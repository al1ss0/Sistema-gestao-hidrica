import pytest

from hidrica import agro


def test_et0_exemplo_fao56():
    valor = float(agro.et0(21.5, 12.3, 70.56, 2.78, 22.07, 50.8, 100, 187))
    assert 3.8 <= valor <= 4.0


def test_kc_milho():
    assert agro.kc("milho", 0) == pytest.approx(0.30)
    assert agro.kc("milho", 70) == pytest.approx(1.20)
    assert 0.30 < agro.kc("milho", 50) < 1.20
    assert agro.kc("milho", 50) == pytest.approx(0.75)
    assert agro.kc("milho", 149) == pytest.approx(0.60, abs=0.05)


def test_taw_milho_medio():
    assert agro.taw("milho", "médio") == pytest.approx(130.0, abs=1e-6)


def test_classificar():
    assert agro.classificar(4.9, 10) == 0
    assert agro.classificar(5, 10) == 1
    assert agro.classificar(9.99, 10) == 1
    assert agro.classificar(10, 10) == 2
