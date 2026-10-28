"""Baralho com repetição espaçada, no estilo do Anki.

Os cartões nascem sozinhos do que o app já sabe de você:
  - frase: cada correção do caderno (frente: o que você disse; verso: a versão certa e o porquê);
  - palavra: cada palavra nova do tutor (frente: o sentido em português e o exemplo com lacuna);
  - livre: os que você ou o Perguntar criam.

O agendamento é o FSRS-4.5 (o algoritmo do Anki atual), com os pesos padrão e retenção de 90%:
cada cartão tem estabilidade (quantos dias até a chance de lembrar cair a 90%) e dificuldade.
Os passos de aprendizado seguem o Anki: errou, volta em 1 minuto; cartão novo com "Bom" volta
em 10 minutos uma vez antes de ganhar dias. O dia vira às 4 da manhã, como no Anki.
"""
import difflib
import json
import math
import re
import threading
from datetime import datetime, timedelta

from . import db, reading, tutor

# Pesos padrão do FSRS-4.5.
W = [0.4872, 1.4003, 3.7145, 13.8206, 5.1618, 1.2298, 0.8975, 0.031, 1.6474, 0.1367, 1.0461,
     2.1072, 0.0793, 0.3246, 1.587, 0.2272, 2.8755]
DECAY = -0.5
FACTOR = 19 / 81  # com isso, R(S) = 90%
RETENTION = 0.9
MAX_DAYS = 365
DAY_START_HOUR = 4
LEARN_MINUTES = {1: 1, 2: 5, 3: 10}  # Errei, Difícil, Bom num cartão novo ou em aprendizado
SOON = timedelta(minutes=20)  # o que volta antes disso aparece de novo na mesma sessão
FIELDS = ("state", "due", "stability", "difficulty", "reps", "lapses", "last_review")


def _iso(d: datetime) -> str:
    return d.isoformat(timespec="seconds")


def day_bounds(now: datetime | None = None) -> tuple[datetime, datetime]:
    now = now or datetime.now()
    start = now.replace(hour=DAY_START_HOUR, minute=0, second=0, microsecond=0)
    if now < start:
        start -= timedelta(days=1)
    return start, start + timedelta(days=1)


# --- FSRS ---------------------------------------------------------------------------------

def _clamp_d(d: float) -> float:
    return min(max(d, 1.0), 10.0)


def _d0(rating: int) -> float:
    return _clamp_d(W[4] - (rating - 3) * W[5])


def _next_d(d: float, rating: int) -> float:
    d2 = d - W[6] * (rating - 3)
    return _clamp_d(W[7] * W[4] + (1 - W[7]) * d2)  # puxa de leve de volta para D0(3), como no FSRS-4.5


def _retrievability(elapsed_days: float, s: float) -> float:
    return (1 + FACTOR * elapsed_days / s) ** DECAY


def _recall_s(d: float, s: float, r: float, rating: int) -> float:
    hard = W[15] if rating == 2 else 1.0
    easy = W[16] if rating == 4 else 1.0
    return s * (1 + math.exp(W[8]) * (11 - d) * s ** -W[9] * (math.exp(W[10] * (1 - r)) - 1) * hard * easy)


def _forget_s(d: float, s: float, r: float) -> float:
    return min(s, W[11] * d ** -W[12] * ((s + 1) ** W[13] - 1) * math.exp(W[14] * (1 - r)))


def _days(s: float) -> int:
    raw = s / FACTOR * (RETENTION ** (1 / DECAY) - 1)
    return int(min(max(round(raw), 1), MAX_DAYS))


def options(c: dict, now: datetime | None = None) -> dict:
    """O que cada botão faria com o cartão: {nota: campos novos}, com "minutes" ou "days" para mostrar."""
    now = now or datetime.now()
    state = c["state"] or "new"
    s, d = c["stability"], c["difficulty"]
    start, _ = day_bounds(now)
    out = {}

    def learn(rating, s_, d_, st):
        mins = LEARN_MINUTES[rating]
        return {"state": st, "due": _iso(now + timedelta(minutes=mins)), "stability": s_, "difficulty": d_,
                "minutes": mins}

    def review(s_, d_, days):
        return {"state": "review", "due": _iso(start + timedelta(days=days)), "stability": s_, "difficulty": d_,
                "days": days}

    if state == "new":
        for g in (1, 2, 3):
            out[g] = learn(g, W[g - 1], _d0(g), "learning")
        out[4] = review(W[3], _d0(4), _days(W[3]))
    elif state in ("learning", "relearning"):
        # Passos do mesmo dia não mexem na estabilidade nem na dificuldade (FSRS-4.5): senão um
        # cartão errado duas vezes seguidas ficava "difícil" demais e crescia devagar para sempre.
        good = _days(s)
        out[1] = learn(1, s, d, state)
        out[2] = learn(2, s, d, state)
        out[3] = review(s, d, good)
        out[4] = review(s, d, max(good + 1, _days(s * 1.5)))
    else:
        last = datetime.fromisoformat(c["last_review"]) if c["last_review"] else now
        r = _retrievability(max((now - last).total_seconds() / 86400, 0), s)
        s_fail = _forget_s(d, s, r)
        out[1] = {"state": "relearning", "due": _iso(now + timedelta(minutes=1)), "stability": s_fail,
                  "difficulty": _next_d(d, 1), "minutes": 1}
        days = {g: _days(_recall_s(d, s, r, g)) for g in (2, 3, 4)}
        days[2] = min(days[2], days[3])  # como no Anki: Difícil ≤ Bom < Fácil
        days[3] = max(days[3], days[2] + 1)
        days[4] = max(days[4], days[3] + 1)
        for g in (2, 3, 4):
            out[g] = review(_recall_s(d, s, r, g), _next_d(d, g), days[g])
    return out


# --- Cartões que nascem do caderno -----------------------------------------------------------

def cloze(word: str, example: str) -> str:
    """O exemplo com a palavra trocada por uma lacuna; vazio se a palavra não aparece nele."""
    core = re.sub(r"^(to|a|an|the)\s+", "", word.strip(), flags=re.I)
    parts = [re.escape(p[:-1] if len(p) > 3 and p.endswith("e") else p) for p in core.split()]
    if not parts or not example:
        return ""
    pat = re.compile(r"\b" + r"\w*\s+".join(parts) + r"\w*", flags=re.I)
    return pat.sub("____", example) if pat.search(example) else ""  # todas as vezes: senão a 2ª entrega


_sync_lock = threading.Lock()  # duas telas sincronizando juntas criavam o mesmo cartão duas vezes


def sync() -> int:
    """Cria os cartões das correções e palavras novas que ainda não estão no baralho."""
    with _sync_lock:
        return _sync()


def _sync() -> int:
    made = 0
    seen = db.card_backs("frase")
    for m in db.uncarded_mistakes():
        better = m["better"].strip()
        if better.lower() in seen or len(better.split()) > 25:
            # Mesmo assim fica registrado, para não ser olhado de novo a cada sincronização.
            db.update_card(db.add_card("frase", m["original"], better, source="caderno", source_id=m["id"],
                                       created_at=m["created_at"]), deleted=1)
            continue
        seen.add(better.lower())
        db.add_card("frase", m["original"].strip(), better, note=m["explanation_pt"] or "", speak=better,
                    hint=tutor.PATTERN_PT.get(m["pattern"], m["pattern"]), source="caderno", source_id=m["id"],
                    created_at=m["created_at"], meaning=m["meaning_pt"] or "")
        made += 1
    seen = db.card_backs("palavra")
    for w in db.uncarded_words():
        word = w["word"].strip()
        if word.lower() in seen:
            db.update_card(db.add_card("palavra", w["meaning_pt"], word, source="palavra", source_id=w["id"],
                                       created_at=w["created_at"]), deleted=1)
            continue
        seen.add(word.lower())
        db.add_card("palavra", w["meaning_pt"], word, note=w["example"], speak=f"{word}. {w['example']}",
                    hint=cloze(word, w["example"]), source="palavra", source_id=w["id"], created_at=w["created_at"])
        made += 1
    return made


# --- Sessão de revisão ------------------------------------------------------------------------

def public(c: dict, now: datetime | None = None) -> dict:
    opts = options(c, now)
    return {
        "id": c["id"], "kind": c["kind"], "front": c["front"], "hint": c["hint"] or "", "back": c["back"],
        "meaning": c["meaning"] or "",
        "note": c["note"] or "", "speak": c["speak"] or "", "state": c["state"], "due": c["due"],
        "reps": c["reps"], "lapses": c["lapses"], "suspended": bool(c["suspended"]), "source": c["source"],
        "stability": c["stability"], "created_at": c["created_at"],
        "options": {g: {k: o[k] for k in ("minutes", "days") if k in o} for g, o in opts.items()},
    }


def per_day() -> int:
    try:
        return max(0, min(int(db.get_settings().get("cards_per_day") or 10), 50))
    except ValueError:
        return 10


def summary(now: datetime | None = None) -> dict:
    now = now or datetime.now()
    start, end = day_bounds(now)
    due = db.cards_due(_iso(end), _iso(now + SOON))
    new_left = max(per_day() - db.new_cards_seen(_iso(start)), 0)
    new_avail = len(db.cards_new(new_left))
    today = db.reviews_since(_iso(start))
    month = [r for r in db.reviews_since(_iso(now - timedelta(days=30))) if r["state"] == "review"]
    tomorrow = db.cards_due(_iso(end + timedelta(days=1)), _iso(end + timedelta(days=1)))
    return {
        "due": len(due), "new": new_avail, "per_day": per_day(), "reviewed_today": len({r["card_id"] for r in today}),
        "retention": (sum(1 for r in month if r["rating"] > 1) / len(month)) if month else None,
        "retention_n": len(month), "tomorrow": max(len(tomorrow) - len(due), 0), "counts": db.deck_counts(),
    }


def session(extra: int = 0) -> dict:
    """A sessão de hoje. `extra`: cartões novos além do limite do dia, quando você pede mais."""
    sync()
    now = datetime.now()
    start, end = day_bounds(now)
    due = db.cards_due(_iso(end), _iso(now + SOON))
    new = db.cards_new(max(per_day() - db.new_cards_seen(_iso(start)), 0) + max(0, min(extra, 50)))
    # Primeiro o que está em aprendizado e as revisões; os novos vêm depois, um a cada três.
    queue, news = list(due), list(new)
    mixed = []
    while queue or news:
        for _ in range(3):
            if queue:
                mixed.append(queue.pop(0))
        if news:
            mixed.append(news.pop(0))
    return {"cards": [public(c, now) for c in mixed], "summary": summary(now)}


def answer(cid: int, rating: int) -> dict:
    c = db.get_card(cid)
    if not c or rating not in (1, 2, 3, 4):
        raise KeyError(cid)
    now = datetime.now()
    o = options(c, now)[rating]
    prev = {k: c[k] for k in FIELDS}
    db.update_card(cid, state=o["state"], due=o["due"], stability=o["stability"], difficulty=o["difficulty"],
                   reps=c["reps"] + 1, lapses=c["lapses"] + (1 if rating == 1 and c["state"] == "review" else 0),
                   last_review=_iso(now))
    db.add_review(cid, rating, c["state"] or "new", o.get("days") or o["minutes"] / 1440, prev)
    c2 = db.get_card(cid)
    again = c2["state"] in ("learning", "relearning") and datetime.fromisoformat(c2["due"]) <= now + SOON
    return {"card": public(c2, now), "again": again, "summary": summary(now)}


def undo() -> dict:
    """Desfaz a última nota de hoje (o botão errado acontece)."""
    start, _ = day_bounds()
    r = db.last_review(_iso(start))  # só de cartões que ainda existem
    if not r or not db.get_card(r["card_id"]):
        raise KeyError("nada")
    db.update_card(r["card_id"], **json.loads(r["prev"]))
    db.delete_review(r["id"])
    return {"card": public(db.get_card(r["card_id"])), "summary": summary()}


# --- Responder escrevendo -------------------------------------------------------------------
# A resposta digitada contra o verso. O app só confere e sugere a nota: quem dá a nota é você,
# porque o FSRS agenda pelo quanto custou lembrar, e isso a comparação não sabe.
SUGGEST = {"certo": 3, "quase": 2, "errado": 1}  # Bom, Difícil, Errei


def _marks(target: str, said: str) -> tuple[list, list]:
    """Palavra a palavra, o que bate entre o verso e o que você escreveu (para marcar na tela).
    A comparação é nas formas por extenso: "It's" e "It is" batem; a marca volta para a palavra escrita."""
    def pieces(text):
        raw = text.split()
        flat, owner = [], []
        for i, w in enumerate(raw):
            for x in reading._expanded(w):
                flat.append(x)
                owner.append(i)
        return raw, flat, owner
    t_raw, t_flat, t_own = pieces(target)
    s_raw, s_flat, s_own = pieces(said)
    t_hit, s_hit = [False] * len(t_flat), [False] * len(s_flat)
    for m in difflib.SequenceMatcher(a=t_flat, b=s_flat, autojunk=False).get_matching_blocks():
        for k in range(m.size):
            t_hit[m.a + k] = s_hit[m.b + k] = True

    def out(raw, own, hit):
        ok = [True] * len(raw)  # pontuação sozinha (um travessão) não tem pedaço e não conta
        for j, i in enumerate(own):
            ok[i] = ok[i] and hit[j]
        return [{"w": w, "ok": ok[i]} for i, w in enumerate(raw)]
    return out(t_raw, t_own, t_hit), out(s_raw, s_own, s_hit)


_LEADING = {"to", "a", "an", "the"}


def _core(words: list) -> list:
    """Sem o "to" do infinitivo nem o artigo da frente: "look after" vale "to look after"."""
    return words[1:] if len(words) > 1 and words[0] in _LEADING else words


def _contains(words: list, part: list) -> bool:
    return any(words[i:i + len(part)] == part for i in range(len(words) - len(part) + 1))


def check(cid: int, text: str) -> dict:
    c = db.get_card(cid)
    if not c or c["deleted"]:
        raise KeyError(cid)
    said = " ".join(text.split())[:500]
    if not said:
        raise ValueError("Escreva a resposta antes de conferir.")
    target = c["back"]
    t, s = reading._expanded(target), reading._expanded(said)  # "doesn't" e "does not" são iguais
    exact = bool(t) and t == s
    # Parecido letra a letra: um erro de digitação ("ofice") é "quase", não "errado".
    near = difflib.SequenceMatcher(a=" ".join(t), b=" ".join(s), autojunk=False).ratio()
    missing, kept = [], []
    if exact:
        verdict = "certo"
    elif c["kind"] == "frase":
        # Escrevendo não há ruído de transcrição: certo é só a frase certa. Fora isso, o que pesa é
        # se o erro ficou (errado) ou se é uma palavra ou grafia a mais ou a menos (quase).
        v = reading.judge_correction(c["front"], target, said, 0)
        missing, kept = v["missing"], v["kept"]
        wrote_original = s == reading._expanded(c["front"])
        verdict = "errado" if kept or wrote_original else "quase" if near >= 0.85 else "errado"
    elif len(t) <= 4 and _contains(s, _core(t)) and len(s) - len(_core(t)) <= 2:
        verdict = "certo"  # resposta curta com ou sem artigo e "to": "the deadline", "look after"
    else:
        words = difflib.SequenceMatcher(a=t, b=s, autojunk=False).ratio()  # frase longa com uma palavra trocada
        verdict = "quase" if near >= 0.85 or words >= 0.85 else "errado"
    answer, yours = _marks(target, said)
    if exact:
        answer = [{**x, "ok": True} for x in answer]
        yours = [{**x, "ok": True} for x in yours]
    return {"verdict": verdict, "suggest": SUGGEST[verdict], "exact": exact, "text": said,
            "answer": answer, "yours": yours, "missing": missing, "kept": kept}


def create(kind: str, front: str, back: str, note: str = "", source: str = "voce") -> int:
    front, back = front.strip()[:400], back.strip()[:400]
    if not front or not back:
        raise ValueError("O cartão precisa de frente e verso.")
    return db.add_card(kind, front, back, note=note.strip()[:600], speak=back, source=source)
