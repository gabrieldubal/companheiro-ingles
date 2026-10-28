"""Ouvir a diferença: pares mínimos em várias vozes, e você escolhe qual palavra ouviu.

É o treino de "várias vozes" (high variability phonetic training): ouvir o mesmo contraste em
falantes diferentes ensina o ouvido a separar os sons, e ajuda a boca a produzir a diferença.
As vozes são as do navegador (americanas, britânicas e outras), sorteadas a cada palavra.
"""
from collections import Counter, defaultdict
from datetime import datetime, timedelta

from . import db, plan, pron

# Em cada par, a primeira palavra tem o som do inglês e a segunda é a troca típica de quem
# fala português. Ficaram de fora as palavras que a voz do navegador lê de dois jeitos (live, read).
PAIRS = {
    "i-short-long": [("ship", "sheep"), ("sit", "seat"), ("fill", "feel"), ("bit", "beat"), ("hit", "heat"),
                     ("chip", "cheap"), ("lip", "leap"), ("still", "steal")],
    "ae-e": [("bad", "bed"), ("man", "men"), ("had", "head"), ("sad", "said"), ("pan", "pen"), ("bag", "beg"),
             ("sat", "set"), ("flash", "flesh")],
    "th-voiceless": [("think", "sink"), ("thank", "tank"), ("three", "tree"), ("thin", "tin"), ("thick", "sick"),
                     ("math", "mass"), ("path", "pass"), ("mouth", "mouse")],
    "th-voiced": [("they", "day"), ("then", "den"), ("though", "dough"), ("there", "dare"), ("breathe", "breed")],
    "dark-l": [("goal", "go"), ("toll", "toe"), ("feel", "fee"), ("seal", "sea"), ("peel", "pea"), ("tool", "two")],
    "r-initial": [("rat", "hat"), ("red", "head"), ("rope", "hope"), ("rot", "hot"), ("ride", "hide"), ("rear", "hear")],
    "aspiration": [("ten", "den"), ("pig", "big"), ("coat", "goat"), ("tie", "die"), ("cap", "gap"), ("pear", "bear")],
}
DEFAULT_MIX = ["i-short-long", "ae-e", "th-voiceless"]  # sem medidas ainda: as vogais e o th


def sets() -> list[dict]:
    return [{"tag": t, "label": pron.LABEL[t], "symbol": pron.SYMBOL[t], "example": pron.EXAMPLE[t],
             "pairs": [list(p) for p in ps]} for t, ps in PAIRS.items()]


def mix_tags() -> list[str]:
    """Os seus sons fracos que têm pares; sem eles, as vogais e o th."""
    weak = [s["tag"] for s in plan.pron_profile() if s["status"] in ("treinar", "atenção") and s["tag"] in PAIRS]
    return weak[:3] or DEFAULT_MIX


def stats(days: int = 30) -> dict:
    now = datetime.now()
    rows = db.listen_trials((now - timedelta(days=days)).isoformat(timespec="seconds"))
    week = (now - timedelta(days=7)).isoformat(timespec="seconds")
    by = defaultdict(list)
    for r in rows:
        by[r["tag"]].append(r)
    out = []
    for s in sets():
        rs = by.get(s["tag"], [])
        recent = [r for r in rs if r["created_at"] >= week]
        misses = Counter(f"{r['word']}→{r['chosen']}" for r in rs if not r["ok"])
        out.append({**s, "n": len(rs), "ok": sum(r["ok"] for r in rs),
                    "week_n": len(recent), "week_ok": sum(r["ok"] for r in recent),
                    "misses": [{"heard": k.split("→")[0], "chose": k.split("→")[1], "n": n}
                               for k, n in misses.most_common(3)]})
    return {"sounds": out, "mix": mix_tags()}


def record(tag: str, word: str, other: str, chosen: str, voice: str) -> bool:
    if tag not in PAIRS or (word, other) not in PAIRS[tag] and (other, word) not in PAIRS[tag]:
        raise KeyError(tag)
    ok = chosen == word
    db.add_listen_trial(tag, word, other, chosen, ok, voice)
    return ok
