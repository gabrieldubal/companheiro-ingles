"""Frases para falar: uma fila escolhida pelos seus sons fracos.

Fontes, todas com o texto certo conhecido (o detector precisa dele):
  - as 24 frases da leitura e as frases dos treinos de som;
  - as frases geradas "do seu mundo" (Claude);
  - as suas próprias frases das conversas, já corrigidas (a versão "better" dos cartões).

Cada frase ganha pontos pelos alvos que tem nos seus sons fracos: um "think" vale para o θ,
um "people" para o l no fim. O próprio detector conta os alvos, então qualquer frase nova
entra sem precisar de etiqueta.
"""
import random
from datetime import date, datetime, timedelta

from . import db, drills, plan, pron, reading


def _targets(text: str) -> dict:
    """Quantos alvos de cada som a frase tem, fingindo que tudo foi dito certo."""
    words = pron.expected(text)
    fake = [{**w, "exp": w["phones"], "pairs": [(p, p) for p in w["phones"]], "before": []} for w in words]
    counts = {}
    for _, tag, *_ in pron.findings(fake):
        counts[tag] = counts.get(tag, 0) + 1
    return counts


def _pool() -> list[dict]:
    pool = [{"text": t, "source": "leitura"} for _, t, *_ in reading.SENTENCES if not t.count(",") >= 2]
    for tag, items in drills.ITEMS.items():
        pool += [{"text": t, "source": "treino"} for t, _ in items if t.endswith(".")]
    for tag in drills.ITEMS:
        pool += [{"text": it["text"], "source": "seu mundo"} for it in db.drill_items(tag)]
    for m in db.corrected_sentences(limit=80):
        pool.append({"text": m, "source": "sua conversa"})
    seen, out = set(), []
    for p in pool:
        key = p["text"].strip().lower()
        if key not in seen and 3 <= len(key.split()) <= 18:
            seen.add(key)
            out.append(p)
    return out


def queue(n: int = 6) -> dict:
    profile = plan.pron_profile()
    weak = [s for s in profile if s["status"] in ("treinar", "atenção")][:4]
    weights = {s["tag"]: max(s["priority"], 0.05) for s in weak}
    focus = plan.focus_sound(profile)
    if focus and focus.get("chosen"):  # escolhido por você: vem na frente
        weights[focus["tag"]] = max(weights.values(), default=1) * 1.5
    if not weights:  # sem medidas ainda: os sons mais difíceis para quem fala português
        weights = {"th-voiceless": 1, "i-short-long": 1, "ed": 1, "ae-e": 0.8, "dark-l": 0.8}
    recent = db.recent_references("frase", since=(datetime.now() - timedelta(days=2)).isoformat(timespec="seconds"))
    rnd = random.Random(str(date.today()))
    candidates = []
    for p in _pool():
        if p["text"] in recent:
            continue
        t = _targets(p["text"])
        if any(tag in weights for tag in t):
            # um pouco de acaso para a fila não ser sempre a mesma; suas frases ganham um empurrão
            bonus = 1.25 if p["source"] in ("sua conversa", "seu mundo") else 1.0
            candidates.append((p, t, bonus * rnd.uniform(0.8, 1.2)))
    # Rodízio entre os sons fracos: sem isso, frases cheias de θ tomavam a fila inteira.
    order = sorted(weights, key=lambda k: -weights[k])
    picked, used = [], set()
    while len(picked) < n and len(used) < len(candidates):
        progress = False
        for tag in order:
            best = max(((min(t.get(tag, 0), 3) * j, i) for i, (p, t, j) in enumerate(candidates)
                        if i not in used and t.get(tag)), default=None)
            if best:
                used.add(best[1])
                picked.append((tag, *candidates[best[1]][:2]))
                progress = True
                if len(picked) >= n:
                    break
        if not progress:
            break
    items = []
    for tag, p, t in picked:
        others = [k for k in sorted(t, key=lambda k: -weights.get(k, 0)) if k in weights and k != tag]
        items.append({**p, "focus": [pron.LABEL[tag]] + [pron.LABEL[k] for k in others[:1]], "tag": tag})
    return {"items": items, "weak": [{"tag": s["tag"], "label": s["label"], "symbol": s["symbol"]} for s in weak]}
