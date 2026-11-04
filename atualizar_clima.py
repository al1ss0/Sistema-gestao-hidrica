"""Atualiza o clima com os dados mais recentes da NASA POWER. Uso: python atualizar_clima.py"""
from hidrica import clima


def main():
    df = clima.atualizar_clima()
    meta = clima.carregar_meta()
    print(f"Clima atualizado: {meta['primeira_data']} a {meta['ultima_data']} ({len(df)} dias)")
    print(f"Fonte: {meta['fonte_nome']}")
    print(f"Tipo: {meta['tipo_dado']}")


if __name__ == "__main__":
    main()
