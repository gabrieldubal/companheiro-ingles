"""Entender: aulas curtas sobre os seus erros, os seus sons e alguns temas que o seu objetivo pede.

Cada aula é feita uma vez pelo Claude com os seus dados e fica guardada: a regra em poucas frases,
por que o português engana, os seus exemplos (errado e certo, tirados do caderno ou do detector),
exemplos novos do seu mundo, um exercício de escolha corrigido na hora e cartões para levar.
"""
from . import db, deck, llm, plan, pron, tutor

# Temas além dos erros: o que uma entrevista ou uma call de trabalho pedem e o caderno ainda não mostra.
TOPICS = {
    "preposicoes-tempo": ("Preposições de tempo: on, in, at",
                          "on/in/at with days, dates, months, parts of the day and 'the final day'"),
    "numeros-horas": ("Números, datas e horários",
                      "saying times (8 a.m., 6 p.m., half past), dates, years, prices and big numbers aloud"),
    "historia-passado": ("Contar uma história no passado",
                         "telling a story in the past: past simple, sequence words (first, then, after that), "
                         "regular -ed pronunciation"),
    "ligacao": ("Como as palavras se ligam na fala rápida",
                "connected speech: linking consonant to vowel (turn_off), weak forms (to, of, can), "
                "gonna/wanna, and why natives sound fast"),
    "silaba-forte": ("A sílaba forte das palavras",
                     "word stress, especially in tech and work words (DAta, aNALysis, deVELoper, PROject vs proJECT)"),
}

_STR = {"type": "string"}
SCHEMA = {
    "type": "object",
    "properties": {
        "title": _STR,
        "rule_pt": _STR,
        "why_pt": _STR,
        "examples": {"type": "array", "items": {
            "type": "object", "properties": {"en": _STR, "pt": _STR}, "required": ["en", "pt"], "additionalProperties": False}},
        "exercise": {"type": "array", "items": {
            "type": "object",
            "properties": {"prompt": _STR, "options": {"type": "array", "items": _STR}, "answer": {"type": "integer"},
                           "explain_pt": _STR},
            "required": ["prompt", "options", "answer", "explain_pt"], "additionalProperties": False}},
        "cards": {"type": "array", "items": {
            "type": "object", "properties": {"front": _STR, "back": _STR}, "required": ["front", "back"],
            "additionalProperties": False}},
    },
    "required": ["title", "rule_pt", "why_pt", "examples", "exercise", "cards"],
    "additionalProperties": False,
}


def _weak() -> list[dict]:
    return [s for s in plan.pron_profile() if s["status"] in ("treinar", "atenção") and s["rate"] >= 0.05]


def trilha() -> list[dict]:
    """A ordem das aulas: os padrões que mais se repetem, os sons fracos e os temas."""
    state = db.lessons_state()
    items = []
    for p in plan.grammar_profile()[:6]:
        items.append({"key": f"padrao:{p['pattern']}", "kind": "padrao", "title": p["label"],
                      "why": f"{p['count']} {'vez' if p['count'] == 1 else 'vezes'} nas suas conversas"})
    for s in _weak()[:4]:
        items.append({"key": f"som:{s['tag']}", "kind": "som", "title": f"O som {s['symbol']}: {s['label']}",
                      "why": f"saiu diferente em {s['off']} de {s['n']} vezes"})
    for slug, (title, _) in TOPICS.items():
        items.append({"key": f"tema:{slug}", "kind": "tema", "title": title, "why": "tema para entrevistas e calls"})
    # Aula guardada continua na trilha mesmo quando o padrão ou o som sai dos primeiros
    # (você corrigiu, ou outros apareceram mais): dá para rever a qualquer hora.
    listed = {it["key"] for it in items}
    for saved in db.lessons_saved():
        kind = saved["key"].partition(":")[0]
        if saved["key"] not in listed and kind in ("padrao", "som", "tema"):
            items.append({"key": saved["key"], "kind": kind, "title": saved["title"], "why": "aula guardada"})
    for it in items:
        st = state.get(it["key"])
        it["ready"] = bool(st)
        it["score"] = st["score"] if st else None
        it["total"] = st["total"] if st else None
        it["done_at"] = st["done_at"] if st else None
    return items


def _your_examples(kind: str, ref: str) -> list[dict]:
    if kind == "padrao":
        return [{"wrong": m["original"], "right": m["better"], "note": m["explanation_pt"] or ""}
                for m in db.notebook_examples(ref)]
    if kind == "som":
        out = []
        for w in db.problem_words("2000-01-01", limit=60):
            if w["tag"] == ref:
                out.append({"wrong": w["word"], "right": w["word"],
                            "note": f"{w['misses']} {'vez' if w['misses'] == 1 else 'vezes'}: {w['what'] or ''}"})
        return out[:5]
    return []


def _subject(kind: str, ref: str) -> str:
    if kind == "padrao":
        return f'the grammar pattern "{ref}" ({tutor.PATTERN_PT.get(ref, ref)})'
    if kind == "som":
        return (f"pronouncing {pron.LABEL.get(ref, ref)} ({pron.SYMBOL.get(ref, '')}, as in {pron.EXAMPLE.get(ref, '')}): "
                "how to make the sound, what Brazilian speakers do instead, and how to check it alone")
    return TOPICS[ref][1]


def get(key: str, refresh: bool = False) -> dict:
    kind, _, ref = key.partition(":")
    if kind not in ("padrao", "som", "tema") or (kind == "tema" and ref not in TOPICS) or \
            (kind == "som" and ref not in pron.LABEL):
        raise KeyError(key)
    saved = None if refresh else db.lesson(key)
    if saved:
        content = saved["content"]
    else:
        content = _generate(kind, ref)
        db.save_lesson(key, content)
        saved = db.lesson(key)
    return {"key": key, "kind": kind, "ref": ref, **content, "yours": _your_examples(kind, ref),
            "score": saved["score"], "total": saved["total"]}


def _generate(kind: str, ref: str) -> dict:
    yours = _your_examples(kind, ref)
    system = ("You are an excellent English teacher writing a short, personal lesson for a Brazilian learner around B1. "
              "Write every *_pt field in natural Brazilian Portuguese, direct and friendly, no textbook tone. "
              "English examples must be natural spoken English.")
    prompt = (
        f"Learner profile (Portuguese):\n{tutor._profile_text()}\n\nLesson subject: {_subject(kind, ref)}.\n"
        + ("The learner's own mistakes or words on this subject:\n"
           + "\n".join(f"- {y['wrong']} -> {y['right']} {y['note']}" for y in yours) + "\n" if yours else "")
        + "\nReturn:\n"
        "- title: the lesson title in Portuguese, short.\n"
        "- rule_pt: the rule or the technique in 2 to 4 short sentences. Only what matters for speaking.\n"
        "- why_pt: 1 or 2 sentences on why Portuguese makes this hard (the exact interference).\n"
        "- examples: 5 short examples about the learner's own life and work, each with en and a pt translation.\n"
        "- exercise: 4 multiple-choice items (2 to 4 options, answer is the 0-based index of the right option). "
        "Use the learner's real mistakes as wrong options when possible. explain_pt: one sentence on why.\n"
        "- cards: 3 flashcards worth remembering: front in Portuguese or an English sentence with ____, back in English."
    )
    data = llm.complete_json(system, prompt, SCHEMA)
    ex = []
    for e in (data.get("exercise") or [])[:5]:
        opts = [str(o) for o in e.get("options") or [] if str(o).strip()]
        a = e.get("answer")
        if 2 <= len(opts) <= 4 and isinstance(a, int) and 0 <= a < len(opts):
            ex.append({"prompt": str(e.get("prompt") or ""), "options": opts, "answer": a,
                       "explain_pt": str(e.get("explain_pt") or "")})
    return {"title": str(data.get("title") or "").strip(), "rule_pt": str(data.get("rule_pt") or "").strip(),
            "why_pt": str(data.get("why_pt") or "").strip(),
            "examples": [x for x in data.get("examples") or [] if x.get("en")][:6], "exercise": ex,
            "cards": [c for c in data.get("cards") or [] if c.get("front") and c.get("back")][:4]}


def add_cards(key: str) -> int:
    saved = db.lesson(key)
    if not saved:
        raise KeyError(key)
    n = 0
    for c in saved["content"].get("cards", []):
        deck.create("livre", c["front"], c["back"], source="entender")
        n += 1
    return n


def next_lesson() -> dict | None:
    """A próxima aula da trilha que você ainda não fez (para o passo do Hoje)."""
    return next((t for t in trilha() if t["score"] is None), None)
