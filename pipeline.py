"""Executa clima -> dataset -> treino. Uso: python pipeline.py [--clima-sintetico]"""
import argparse

import config
from hidrica import clima, dataset, modelo


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clima-sintetico", action="store_true", help="não baixa a NASA POWER")
    args = parser.parse_args()

    print("1/3 Clima...")
    df_clima = clima.preparar_clima(sintetico=args.clima_sintetico)
    print(f"    {len(df_clima)} dias de {df_clima.index.min().date()} a {df_clima.index.max().date()}")
    print("2/3 Dataset...")
    df = dataset.gerar_dataset(df_clima)
    print(f"    {len(df)} linhas")
    print("3/3 Treino e comparação dos modelos...")
    modelo.treinar_e_avaliar(df)
    print()
    print((config.REPORTS_DIR / "selecao.txt").read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
