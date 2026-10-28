"""Lança uma versão para os amigos: fecha o changelog, sobe o número e gera o zip (só o código, sem nada seu).

    empacotar.bat 2.2.0       lança a 2.2.0 com o que está em "Não lançado" no CHANGELOG.md
    empacotar.bat             refaz o zip da versão atual, se ele não estiver em dist/
    empacotar.bat --de-novo   refaz o zip da versão atual mesmo que ele exista

Entre um lançamento e outro, cada mudança entra no CHANGELOG.md, em "Não lançado"; o zip só sai
quando a versão fecha. Entra no zip: app/, static/, requirements.txt, VERSION, CHANGELOG.md e os
arquivos de tools/pacote/ (instalar.bat, abrir.bat, LEIA-ME.txt, COMO-USAR.txt).
Fica de fora tudo que é seu ou só seu: data/, .env, .venv/, infra/, lab/, perfil.md, vocabulario.txt,
run.bat, celular.bat, README.md. No fim, o zip é conferido: se aparecer algo pessoal, o script falha.
"""
import re
import sys
import zipfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
VERSION = ROOT / "VERSION"
CHANGELOG = ROOT / "CHANGELOG.md"
UNRELEASED = "## Não lançado"
FOLDER = "Companheiro de ingles"
INCLUDE_DIRS = ["app", "static"]
INCLUDE_FILES = ["requirements.txt"]
EXTRA = ROOT / "tools" / "pacote"
FORBIDDEN_NAMES = {".env", "perfil.md", "vocabulario.txt", "proxy.json", "token.txt", "cenarios.json", "companheiro.db",
                   "terraform.tfvars", "run.bat", "celular.bat"}
FORBIDDEN_TEXT = ["RoofScan", "AKIA", "BEDROCK_SECRET", "eqtlab", "Gabriel"]  # nada disso pode ir no código


def files():
    for d in INCLUDE_DIRS:
        for p in sorted((ROOT / d).rglob("*")):
            if p.is_file() and "__pycache__" not in p.parts and p.suffix not in (".pyc", ".pyo"):
                yield p, Path(FOLDER) / p.relative_to(ROOT)
    for name in INCLUDE_FILES:
        yield ROOT / name, Path(FOLDER) / name
    for p in sorted(EXTRA.iterdir()):
        yield p, Path(FOLDER) / p.name


def _num(v: str) -> tuple:
    return tuple(int(x) for x in v.split("."))


def close_version(text: str, new: str) -> str:
    """O que está em "Não lançado" vira a versão nova, com a data; um "Não lançado" vazio fica em cima."""
    if UNRELEASED not in text:
        sys.exit(f'O CHANGELOG.md não tem a seção "{UNRELEASED}".')
    head, rest = text.split(UNRELEASED, 1)
    body, sep, tail = rest.partition("\n## ")
    if not any(line.strip().startswith("- ") for line in body.splitlines()):
        sys.exit(f'Nada em "{UNRELEASED}" no CHANGELOG.md: escreva o que mudou antes de lançar.')
    section = f"## {new} ({date.today():%d/%m/%Y})\n\n{body.strip()}\n"
    return f"{head}{UNRELEASED}\n\n{section}" + (f"\n## {tail}" if sep else "")


def main():
    args = [a for a in sys.argv[1:] if a != "--de-novo"]
    again = "--de-novo" in sys.argv[1:]
    current = VERSION.read_text(encoding="utf-8").strip()
    changelog = CHANGELOG.read_text(encoding="utf-8")
    version = current
    if args:
        version = args[0].lstrip("vV")
        if not re.fullmatch(r"\d+\.\d+\.\d+", version):
            sys.exit(f"Use um número como 2.2.0 (a versão atual é {current}).")
        if _num(version) <= _num(current):
            sys.exit(f"A versão atual já é {current}: use um número maior.")
        changelog = close_version(changelog, version)
    DIST.mkdir(exist_ok=True)
    out = DIST / f"companheiro-de-ingles-{version}.zip"
    if out.exists() and not again:
        a, b, _ = _num(current)
        sys.exit(f"{out.name} já existe em dist/.\n"
                 f"Para lançar uma versão nova: empacotar.bat {a}.{b + 1}.0 (com as mudanças em \"Não lançado\").\n"
                 "Para refazer este mesmo zip: empacotar.bat --de-novo")
    tmp = out.with_suffix(".tmp")
    problems = [f"CHANGELOG.md contém {t!r}" for t in FORBIDDEN_TEXT if t in changelog]
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        for src, arc in files():
            if src.name in FORBIDDEN_NAMES:
                problems.append(f"arquivo pessoal: {arc}")
                continue
            if src.suffix in (".py", ".js", ".html", ".txt", ".bat", ".css", ".json", ".md"):
                text = src.read_text(encoding="utf-8", errors="ignore")
                problems += [f"{arc} contém {t!r}" for t in FORBIDDEN_TEXT if t in text]
            z.write(src, arc.as_posix())
        # O número e as novidades vão como ficam depois do lançamento.
        z.writestr(f"{FOLDER}/VERSION", version + "\n")
        z.writestr(f"{FOLDER}/CHANGELOG.md", changelog)
    if problems:
        tmp.unlink()
        sys.exit("Pacote NÃO gerado (nada foi mudado):\n  " + "\n  ".join(problems))
    tmp.replace(out)
    if args:  # só depois do zip pronto: se algo falhar, o VERSION e o CHANGELOG ficam como estavam
        VERSION.write_text(version + "\n", encoding="utf-8")
        CHANGELOG.write_text(changelog, encoding="utf-8")
    with zipfile.ZipFile(out) as z:
        names = z.namelist()
    size = out.stat().st_size / 1e6
    print(f"Versão {version}: {out}  ({len(names)} arquivos, {size:.1f} MB)")


if __name__ == "__main__":
    main()
