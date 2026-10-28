"""Na instalação: baixa os modelos de voz uma vez, para o app já abrir pronto na primeira vez.

    .venv\\Scripts\\python -m app.preparar
"""
import sys

from . import config, pron, stt


def main():
    print(f"  Pasta dos seus dados: {config.DATA}")
    print("  Baixando o reconhecimento de fala (Whisper, uns 500 MB)...")
    stt.load()
    print("  Baixando o detector de pronúncia (uns 1,2 GB)...")
    if pron.load() is None:
        print(f"  O detector de pronúncia não carregou: {pron.status()}")
        sys.exit(1)
    import cmudict  # noqa: F401  (dicionário de pronúncia)
    import wordfreq  # noqa: F401
    print("  Modelos prontos.")


if __name__ == "__main__":
    main()
