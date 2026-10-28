"""Plano de estudos: o que treinar hoje, por quê, e como você está indo.

As prioridades saem dos seus dados:
  - pronúncia: sons em que a sua taxa de "diferente" fica acima do ruído medido em nativos;
  - gramática: padrões do caderno na hora de revisar (caixas de Leitner), pelo número de vezes.

A sessão do dia é curta de propósito (uns 15 minutos) e a meta é por semana, não por dia:
perder um dia não zera nada.
"""
import math
from collections import defaultdict
from datetime import date, datetime, timedelta

from . import db, deck, drills, lessons, listen, pron, reading, tutor

MIN_CHECKS = 5  # abaixo disso, o som fica como "pouco dado"


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return 0.0, 1.0
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, c - h), min(1.0, c + h)


def _since(days: int) -> str:
    return (datetime.now() - timedelta(days=days)).isoformat(timespec="seconds")


# --- Pronúncia ---------------------------------------------------------------------

def pron_profile(days: int = 60) -> list[dict]:
    """Um resumo por som: sua taxa, a dos nativos, o veredito e os exemplos mais recentes."""
    checks = db.pron_checks(since=_since(days))
    by = defaultdict(list)
    for c in checks:
        by[c["tag"]].append(c)
    out = []
    for tag in pron.LABEL:
        rows = by.get(tag, [])
        n = len(rows)
        off = sum(1 for r in rows if not r["ok"])
        nk, nn = pron.NATIVE_RATE.get(tag, (0, 1))
        native = nk / nn
        _, native_hi = wilson(nk, nn)
        lo, hi = wilson(off, n)
        rate = off / n if n else 0.0
        if n < MIN_CHECKS:
            status = "pouco dado"
        elif lo > native_hi:
            status = "treinar"
        elif rate <= native_hi + 0.05:
            status = "ok"
        else:
            status = "atenção"
        examples = [{"word": r["word"], "what": r["what"], "recording_id": r["recording_id"],
                     "start": r["start"], "end": r["end"], "source": r["kind"], "date": r["created_at"]}
                    for r in rows if not r["ok"]][:6]
        out.append({
            "tag": tag, "label": pron.LABEL[tag], "symbol": pron.SYMBOL[tag], "example": pron.EXAMPLE[tag],
            "n": n, "off": off, "rate": rate, "ci": [lo, hi], "native": native, "status": status,
            "priority": (rate - native) * pron.WEIGHT.get(tag, 0.5) if status in ("treinar", "atenção") else 0,
            "examples": examples, "tip": drills.TIPS.get(tag),
        })
    order = {"treinar": 0, "atenção": 1, "pouco dado": 2, "ok": 3}
    out.sort(key=lambda t: (order[t["status"]], -t["priority"], -t["n"]))
    return out


def focus_sound(profile: list[dict] | None = None) -> dict | None:
    profile = profile if profile is not None else pron_profile()
    chosen = db.get_settings().get("focus_tag")  # escolhido por você (pelo Perguntar)
    hit = next((t for t in profile if t["tag"] == chosen), None) if chosen else None
    if hit:
        return {**hit, "chosen": True}
    targets = [t for t in profile if t["status"] in ("treinar", "atenção")]
    if not targets:
        return None
    # Revezamento leve: se o primeiro já foi treinado hoje, sugere o segundo.
    trained = {a["ref"] for a in db.activity(date.today().isoformat()) if a["kind"] == "treino"}
    for t in targets:
        if t["tag"] not in trained:
            return t
    return targets[0]


# --- Gramática -----------------------------------------------------------------------

def grammar_profile() -> list[dict]:
    nb = db.notebook()
    for p in nb["patterns"]:
        p["label"] = tutor.PATTERN_PT.get(p["pattern"], p["pattern"])
    nb["patterns"].sort(key=lambda p: (not p["due"], -p["count"]))
    return nb["patterns"]


# --- Hoje e a semana -----------------------------------------------------------------------

def week() -> dict:
    settings = db.get_settings()
    target = int(settings.get("weekly_target") or 3)
    today = date.today()
    start = today - timedelta(days=today.weekday())  # segunda-feira
    acts = db.activity((start - timedelta(weeks=8)).isoformat())
    per_day = defaultdict(int)
    for a in acts:
        per_day[a["created_at"][:10]] += a["seconds"]
    days = []
    for i in range(7):
        d = start + timedelta(days=i)
        days.append({"date": d.isoformat(), "minutes": round(per_day.get(d.isoformat(), 0) / 60),
                     "today": d == today, "future": d > today})
    # Um dia "conta" com pelo menos 5 minutos de prática.
    done = sum(1 for d in days if d["minutes"] >= 5)
    streak = 0
    for w in range(1, 9):
        ws = start - timedelta(weeks=w)
        count = sum(1 for i in range(7) if per_day.get((ws + timedelta(days=i)).isoformat(), 0) >= 300)
        if count >= target:
            streak += 1
        else:
            break
    return {"target": target, "done": done, "days": days, "streak_weeks": streak,
            "minutes": sum(d["minutes"] for d in days)}


def _next_scenario() -> str:
    """Rodízio: o cenário feito há mais tempo (os da pessoa vêm primeiro no empate)."""
    last = {}
    for s in db.history(limit=60):
        last.setdefault(s["scenario"], s["started_at"])
    options = [k for k in tutor.scenarios() if k != "diagnostico"]
    return min(options, key=lambda sc: last.get(sc, ""))


# Com voz, o que só dá para fazer falando; sem voz, o que dá para fazer em silêncio (com fone).
# Os passos entram nessa ordem até completar a duração da sessão; o resto fica para "se sobrar tempo".
# A sessão termina sempre com fala livre: corrigir e imitar só valem se a correção aparecer falando.
ORDER_VOICE = ["leitura", "frases", "imitar", "escada", "fale-certo", "cartoes", "ouvir"]
ORDER_SILENT = ["cartoes", "entender", "ouvir", "fale-certo"]


def _fit(steps: list[dict], budget: int) -> tuple[list[dict], list[dict]]:
    main, later, used = [], [], 0
    for s in steps:
        if s["done"]:
            main.append(s)
        elif used + s["minutes"] <= budget or not any(not m["done"] for m in main):
            main.append(s)  # sempre há pelo menos um passo por fazer, mesmo maior que a sessão
            used += s["minutes"]
        else:
            later.append(s)
    return main, later


def today(silent: bool = False) -> dict:
    profile = pron_profile()
    focus = focus_sound(profile)
    done_today = defaultdict(int)
    for a in db.activity(date.today().isoformat()):
        done_today[a["kind"]] += a["seconds"]
    steps = {}
    deck.sync()
    cards = deck.summary()
    n = cards["due"] + cards["new"]
    if n or cards["reviewed_today"]:
        steps["cartoes"] = {
            "kind": "cartoes", "minutes": max(2, round(n * 10 / 60)), "done": not n,
            "title": "Cartões",
            "detail": (f"{n} {'cartão' if n == 1 else 'cartões'} ({cards['new']} {'novo' if cards['new'] == 1 else 'novos'}): "
                       "as suas correções e palavras. Dá para fazer em silêncio.") if n
                      else f"{cards['reviewed_today']} revisados hoje. " + (
                          f"Amanhã {'volta 1' if cards['tomorrow'] == 1 else 'voltam ' + str(cards['tomorrow'])}."
                          if cards["tomorrow"] else "Amanhã não há revisões marcadas."),
        }
    practice = db.practice_items(limit=4)
    if practice:
        steps["fale-certo"] = {
            "kind": "fale-certo", "minutes": 3, "count": len(practice), "done": done_today["fale-certo"] > 60,
            "mode": "escrever" if silent else "falar",
            "title": "Fale certo, por escrito" if silent else "Fale certo",
            "detail": f"{len(practice)} erros seus da conversa, para " +
                      ("escrever do jeito certo, sem olhar a resposta." if silent else "dizer do jeito certo em voz alta."),
            "patterns": [tutor.PATTERN_PT.get(p["pattern"], p["pattern"]) for p in practice],
        }
    heard = next((s for s in listen.stats(days=7)["sounds"] if focus and s["tag"] == focus["tag"]), None)
    ear_ok = heard and heard["n"] >= 20 and heard["ok"] / heard["n"] >= 0.9  # o ouvido já separa esse som
    if focus and focus["tag"] in listen.PAIRS and not ear_ok:
        steps["ouvir"] = {
            "kind": "ouvir", "tag": focus["tag"], "minutes": 3, "done": done_today["ouvir"] > 60,
            "title": f"Ouvir a diferença: {focus['symbol']}",
            "detail": f"{', '.join(' ou '.join(p) for p in listen.PAIRS[focus['tag']][:2])}… em vozes diferentes. "
                      "Você escolhe qual palavra ouviu." + (" Com fone." if silent else ""),
        }
    elif silent:  # o som da vez não tem pares (ou o ouvido já separa): os seus sons fracos misturados
        steps["ouvir"] = {
            "kind": "ouvir", "tag": "misturado", "minutes": 3, "done": done_today["ouvir"] > 60,
            "title": "Ouvir a diferença", "detail": "Pares dos seus sons fracos, em vozes diferentes. Com fone.",
        }
    if focus:
        weak = [s["label"] for s in profile if s["status"] in ("treinar", "atenção")][:3]
        if focus["label"] not in weak:
            weak = [focus["label"]] + weak[:2]
        steps["frases"] = {
            "kind": "frases", "minutes": 4, "done": done_today["frases"] > 120,
            "title": "Frases para falar",
            "detail": f"Frases com os seus sons fracos ({', '.join(weak)}). Clique numa palavra marcada para ver o "
                      "som que saiu trocado e como corrigir.",
        }
        since = (datetime.now() - timedelta(days=90)).isoformat(timespec="seconds")
        open_words = [w for w in db.problem_words(since, limit=40) if not w["mastered"]]
        if open_words:
            w = open_words[0]
            heard_as = None
            rec = db.get_recording(w["recording_id"]) if w.get("recording_id") else None
            if rec:  # "soou como": refeito dos sons guardados, sem rodar o modelo
                hit = next((x for x in pron.realign(rec) if x["word"].lower() == w["word"] and not x["ok"]), None)
                heard_as = hit["sounds_like"] if hit else None
            steps["escada"] = {
                "kind": "escada", "tag": w["tag"], "word": w["word"], "sentence": w["sentence"], "minutes": 3,
                "heard_as": heard_as,
                "done": done_today["escada"] > 60,
                "title": f"Corrigir uma palavra: {w['word']}",
                "detail": f"O {pron.LABEL[w['tag']]} saiu trocado {w['misses']} {'vez' if w['misses'] == 1 else 'vezes'}. "
                          "Uma escada curta, do som sozinho até a frase.",
            }
    scenario = _next_scenario()
    title = tutor.scenarios()[scenario]["title"]
    steps["conversa"] = {
        "kind": "conversa", "scenario": scenario, "minutes": 7, "done": done_today["conversa"] > 180,
        "mode": "escrever" if silent else "falar",
        "title": f"Conversa por escrito: {title}" if silent else f"Conversa: {title}",
        "detail": "O mesmo tutor, digitando. As respostas não são lidas em voz alta." if silent
                  else "O tutor puxa os seus erros que estão na hora de revisar.",
    }
    # Só conta a última rodada de verdade: terminada e com pelo menos metade das frases.
    # Uma rodada aberta e abandonada não pode esconder o retrato do mês por 4 semanas.
    runs = [r for r in db.reading_runs(limit=20) if r["finished_at"] and r["recorded"] >= len(reading.SENTENCES) // 2]
    last_run = runs[0]["started_at"][:10] if runs else None
    if not last_run or (date.today() - date.fromisoformat(last_run)).days >= 28:
        steps["leitura"] = {
            "kind": "leitura", "minutes": 10, "done": done_today["leitura"] > 120,
            "title": "Retrato do mês" if last_run else "Primeiro retrato da pronúncia",
            "detail": "As mesmas 24 frases de sempre, para medir o que mudou." if last_run
                      else "24 frases curtas que medem os sons difíceis.",
        }
    steps["imitar"] = {
        "kind": "imitar", "minutes": 4, "done": done_today["imitar"] > 120, "title": "Imitar um texto",
        "detail": "Um texto curto com as suas frases: ouça o nativo e repita no mesmo ritmo. O app mede os sons e o "
                  "tempo, e a velocidade sobe até a normal.",
    }
    steps["usar"] = {
        "kind": "usar", "minutes": 3, "done": done_today["usar"] > 60, "title": "Com as suas palavras",
        "detail": "Fala livre: uma pergunta que puxa o que você corrigiu. Você responde falando, e o app confere se a "
                  "correção apareceu.",
    }
    nxt = lessons.next_lesson()
    if nxt:
        steps["entender"] = {
            "kind": "entender", "key": nxt["key"], "minutes": 5, "done": done_today["entender"] > 120,
            "title": f"Entender: {nxt['title']}",
            "detail": f"Uma aula curta com os seus exemplos e um exercício ({nxt['why']}).",
        }
    settings = db.get_settings()
    budget = int(settings.get("session_minutes") or 15)
    # O último passo é fala livre. Com voz: conversa, se a última foi há mais de 2 dias; senão, a
    # pergunta que puxa a correção. Sem voz: a conversa por escrito.
    talked = any(a["kind"] == "conversa" and a["seconds"] >= 180
                 for a in db.activity((date.today() - timedelta(days=2)).isoformat()))
    final = steps["conversa"] if silent or not talked else steps["usar"]
    ordered = [steps[k] for k in (ORDER_SILENT if silent else ORDER_VOICE) if k in steps]
    main, later = _fit(ordered, max(budget - final["minutes"], 0))
    main.append(final)
    if not silent:
        later.append(steps["usar"] if final is steps["conversa"] else steps["conversa"])
    return {"focus": focus, "steps": main, "later": later, "silent": silent, "budget": budget, "week": week(),
            "goal": settings.get("goal", ""), "pron_ready": pron.status() == "pronto", "pron_pending": pron.pending()}


# --- Progresso -----------------------------------------------------------------------------

def _week_start(iso: str) -> str:
    d = date.fromisoformat(iso[:10])
    return (d - timedelta(days=d.weekday())).isoformat()


def progress() -> dict:
    today_ = date.today()
    start = today_ - timedelta(days=today_.weekday()) - timedelta(weeks=7)
    weeks = [(start + timedelta(weeks=i)).isoformat() for i in range(8)]
    minutes = defaultdict(int)
    days_active = defaultdict(set)
    for a in db.activity(start.isoformat()):
        ws = _week_start(a["created_at"])
        minutes[ws] += a["seconds"]
        days_active[ws].add(a["created_at"][:10])
    activity_weeks = [{"week": w, "minutes": round(minutes[w] / 60), "days": len(days_active[w])} for w in weeks]

    # Pronúncia por semana, para os sons com mais dados.
    checks = db.pron_checks(since=_since(180))
    per = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    for c in checks:
        cell = per[c["tag"]][_week_start(c["created_at"])]
        cell[0] += int(not c["ok"])
        cell[1] += 1
    sounds = []
    for tag, cells in per.items():
        n = sum(v[1] for v in cells.values())
        if n < MIN_CHECKS:
            continue
        nk, nn = pron.NATIVE_RATE.get(tag, (0, 1))
        points = [{"week": w, "off": v[0], "n": v[1], "rate": v[0] / v[1]} for w, v in sorted(cells.items())]
        sounds.append({"tag": tag, "label": pron.LABEL[tag], "symbol": pron.SYMBOL[tag], "n": n,
                       "native": nk / nn, "points": points})
    rank = {s["tag"]: i for i, s in enumerate(pron_profile(days=180))}  # mesma ordem de "Meus erros"
    sounds.sort(key=lambda s: rank.get(s["tag"], 99))

    convo = [c for c in db.conversation_stats() if c["answers"]]
    for c in convo:
        c["errors_per_100"] = round(100 * c["errors"] / c["words"], 1) if c["words"] else None
        c["words_per_answer"] = round(c["words"] / c["answers"]) if c["answers"] else None
    total_minutes = round(sum(a["seconds"] for a in db.activity("2000-01-01")) / 60)
    return {"weeks": activity_weeks, "sounds": sounds[:8], "conversations": convo, "sessions": study_sessions(),
            "totals": {"minutes": total_minutes, "conversations": len(convo),
                       "words": sum(c["words"] for c in convo), "checks": len(checks)},
            "target": int(db.get_settings().get("weekly_target") or 3)}


# --- Sessões de estudo -------------------------------------------------------------------------
# Uma sessão é um bloco de prática sem pausa maior que 30 minutos. Os resultados (sons, Fale certo,
# cartões, ouvido, conversa) entram na sessão em que aconteceram.
SESSION_GAP = timedelta(minutes=30)
KIND_PT = {"conversa": "Conversa", "treino": "Treino de som", "fale-certo": "Fale certo", "leitura": "Leitura",
           "frases": "Frases", "escada": "Corrigir palavra", "cartoes": "Cartões", "ouvir": "Ouvir",
           "perguntar": "Perguntar"}


def study_sessions(days: int = 60, limit: int = 40) -> list[dict]:
    rows = db.activity((datetime.now() - timedelta(days=days)).isoformat(timespec="seconds"))
    spans = sorted(((datetime.fromisoformat(a["created_at"]) - timedelta(seconds=a["seconds"]),
                     datetime.fromisoformat(a["created_at"]), a) for a in rows), key=lambda x: x[0])
    groups = []
    for start, end, a in spans:
        if groups and start <= groups[-1]["end"] + SESSION_GAP:
            groups[-1]["end"] = max(groups[-1]["end"], end)
            groups[-1]["rows"].append(a)
        else:
            groups.append({"start": start, "end": end, "rows": [a]})
    groups = [g for g in groups if sum(r["seconds"] for r in g["rows"]) >= 60]
    if not groups:
        return []
    lo = (groups[0]["start"] - timedelta(minutes=5)).isoformat(timespec="seconds")
    checks, practice = db.pron_checks(since=lo), db.practice_since(lo)
    reviews, trials = db.reviews_since(lo), db.listen_trials(lo)
    lessons_done = db.lessons_done(lo)
    convos = [c for c in db.conversation_stats() if c["answers"]]
    # Só os sons que você está treinando: o "sem vogal no fim", que você acerta quase sempre,
    # é a maior parte das checagens e deixava a conta bonita demais.
    weak = [t["tag"] for t in pron_profile() if t["status"] in ("treinar", "atenção") and t["rate"] >= 0.05]
    out = []
    for g in groups:
        a = (g["start"] - timedelta(minutes=3)).isoformat(timespec="seconds")
        b = (g["end"] + timedelta(minutes=3)).isoformat(timespec="seconds")
        inside = lambda t: bool(t) and a <= t <= b
        kinds = defaultdict(int)
        for r in g["rows"]:
            kinds[r["kind"]] += r["seconds"]
        cs = [c for c in checks if inside(c["created_at"]) and c["tag"] in weak]
        per = defaultdict(lambda: [0, 0])
        for c in cs:
            per[c["tag"]][0] += int(not c["ok"])
            per[c["tag"]][1] += 1
        pr = [p for p in practice if inside(p["created_at"])]
        rv = [r for r in reviews if inside(r["reviewed_at"])]
        tr = [t for t in trials if inside(t["created_at"])]
        cv = [c for c in convos if inside(c["date"])]
        ls = [x for x in lessons_done if inside(x["done_at"])]
        out.append({
            "start": g["start"].isoformat(timespec="minutes"), "end": g["end"].isoformat(timespec="minutes"),
            "minutes": max(1, round(sum(kinds.values()) / 60)),
            "kinds": [{"kind": k, "label": KIND_PT.get(k, k), "minutes": max(1, round(v / 60))}
                      for k, v in sorted(kinds.items(), key=lambda x: -x[1])],
            "pron": {"n": len(cs), "off": sum(1 for c in cs if not c["ok"]),
                     "sounds": sorted(({"tag": t, "label": pron.LABEL.get(t, t), "symbol": pron.SYMBOL.get(t, ""),
                                        "off": v[0], "n": v[1]} for t, v in per.items()), key=lambda s: weak.index(s["tag"]))},
            "practice": {"n": len(pr), "ok": sum(p["ok"] for p in pr)},
            "cards": {"n": len(rv), "ok": sum(1 for r in rv if r["rating"] > 1)},
            "listen": {"n": len(tr), "ok": sum(t["ok"] for t in tr)},
            "lessons": [{"title": x["title"], "score": x["score"], "total": x["total"]} for x in ls],
            "conversations": [{"title": tutor.scenarios().get(c["scenario"], {}).get("title", c["scenario"]),
                               "words": c["words"], "errors": c["errors"],
                               "errors_per_100": round(100 * c["errors"] / c["words"], 1) if c["words"] else None}
                              for c in cv],
        })
    return out[::-1][:limit]
