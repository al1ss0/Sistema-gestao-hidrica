import pytest

from hidrica import clima as mod_clima
from hidrica import dataset, modelo


@pytest.fixture(scope="session")
def modelo_treinado(clima, tmp_path_factory):
    """Dataset completo (sintético) + treino rápido, gravados em pasta temporária."""
    pasta = tmp_path_factory.mktemp("saida")
    df = dataset.gerar_dataset(clima, salvar=False)
    resultado = modelo.treinar_e_avaliar(df, pasta, rapido=True)
    return pasta, df, resultado


@pytest.fixture(scope="session")
def clima():
    """Clima sintético com ET0, sem depender da internet."""
    return mod_clima.adicionar_et0(mod_clima.gerar_clima_sintetico())
