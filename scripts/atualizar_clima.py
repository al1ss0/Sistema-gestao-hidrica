"""Atualiza o clima com os dados mais recentes da NASA POWER. Uso: python scripts/atualizar_clima.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # raiz do projeto (config, hidrica)

from hidrica import clima


def main():
    df = clima.atualizar_clima()
    meta = clima.carregar_meta()
    print(f"Clima atualizado: {meta['primeira_data']} a {meta['ultima_data']} ({len(df)} dias)")
    print(f"Fonte: {meta['fonte_nome']}")
    print(f"Tipo: {meta['tipo_dado']}")


if __name__ == "__main__":
    main()
