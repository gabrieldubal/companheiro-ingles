"""Guarda no caderno do app erros de inglês que vieram de fora das conversas (por exemplo, as
correções que o Claude Code faz nas suas mensagens). Mesmo caminho das correções do tutor:
entram no Fale certo (o padrão fica na hora de revisar) e viram cartões.

    .venv\\Scripts\\python tools\\guardar_erros.py erros.json

erros.json é uma lista de correções:
    [{"original": "another doubt", "better": "another question",
      "explanation_pt": "...", "pattern": "false friend", "meaning_pt": "outra dúvida"}]
"pattern" tem que ser um dos padrões do app (tutor.PATTERN_PT). Antes de gravar, faz uma cópia do
banco em data/backups/ (uma por dia). Correção que já está no caderno não entra de novo.
"""
import json
import sqlite3
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import config, db, deck, tutor  # noqa: E402

FIELDS = ("original", "better", "explanation_pt", "pattern", "meaning_pt")


def backup() -> Path:
    out = config.DATA / "backups" / f"antes-dos-erros-de-fora-{date.today():%Y%m%d}.db"
    if not out.exists():
        out.parent.mkdir(parents=True, exist_ok=True)
        src, dst = sqlite3.connect(config.DATA / "companheiro.db"), sqlite3.connect(out)
        src.backup(dst)  # seguro com o app ligado
        dst.close()
        src.close()
    return out


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    items = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    bad = [c for c in items if any(not str(c.get(k, "")).strip() for k in FIELDS) or c["pattern"] not in tutor.PATTERN_PT]
    if bad:
        sys.exit("Correção incompleta ou com padrão que o app não conhece:\n" + "\n".join(json.dumps(c, ensure_ascii=False) for c in bad)
                 + "\nPadrões: " + ", ".join(tutor.PATTERN_PT))
    have = {(m["original"].strip().lower(), m["better"].strip().lower())
            for m in db._q("SELECT original, better FROM mistakes")}
    new = [c for c in items if (c["original"].strip().lower(), c["better"].strip().lower()) not in have]
    if not new:
        print("Nada novo: essas correções já estão no caderno.")
        return
    print("cópia:", backup())
    counts = {}
    for c in new:
        counts[c["pattern"]] = counts.get(c["pattern"], 0) + 1
    db.record_feedback(None, [{k: c[k].strip() for k in FIELDS} for c in new],
                       [{"pattern": p, "count": n} for p, n in counts.items()], [], [])
    made = deck.sync()
    print(f"{len(new)} guardados ({len(items) - len(new)} já estavam), {made} cartões novos:")
    for c in new:
        print(f"  {c['original']}  ->  {c['better']}  ({tutor.PATTERN_PT[c['pattern']]})")


if __name__ == "__main__":
    main()
