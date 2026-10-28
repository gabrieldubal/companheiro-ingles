"""Perguntar: uma IA de inglês que conhece os seus dados e pode mexer no seu estudo.

Ela responde dúvidas ("por que é have been aqui?", "como digo prazo?") usando os seus erros e
os seus sons, e age: cria cartões, guarda palavras, põe frases no treino de um som, muda o som
da vez, a meta e o objetivo. Toda ação aparece na resposta com um botão de desfazer.
"""
from . import db, deck, drills, listen, llm, plan, pron, tutor

ACTIONS = ["criar_cartao", "guardar_palavra", "frase_treino", "som_da_vez", "meta_semana", "objetivo", "abrir"]

_STR = {"type": "string"}
SCHEMA = {
    "type": "object",
    "properties": {
        "reply": _STR,
        "actions": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "type": {"type": "string", "enum": ACTIONS},
                "front": _STR, "back": _STR, "note": _STR,
                "word": _STR, "meaning_pt": _STR, "example": _STR,
                "tag": _STR, "text": _STR, "value": _STR,
            },
            "required": ["type", "front", "back", "note", "word", "meaning_pt", "example", "tag", "text", "value"],
            "additionalProperties": False,
        }},
    },
    "required": ["reply", "actions"],
    "additionalProperties": False,
}

# Telas que a resposta pode sugerir abrir (o resto da rota é conferido abaixo).
SCREENS = {
    "#/frases": "Frases para falar: sentences with the student's weak sounds, with a per-word x-ray",
    "#/treino/<tag>": "sound drill for one sound",
    "#/ouvir/<tag>": "listening drill: minimal pairs in several voices",
    "#/cartoes": "flashcard review",
    "#/fale-certo": "say their own corrected sentences aloud",
    "#/leitura": "the 24-sentence read-aloud benchmark",
    "#/conversar/<scenario>": "voice conversation; scenarios: (the ids listed in the study state below)",
    "#/erros/gramatica": "their grammar notebook",
    "#/pronuncia": "pronunciation overview and words to fix",
}

SYSTEM = """You are the English teacher built into a Brazilian student's personal study app. Below you get everything the app knows about them: their own notes, their goal, their pronunciation and grammar data.

# How to answer
- Write "reply" in Brazilian Portuguese, like a friend who happens to be an excellent teacher: direct, warm, no flattery, no filler, no textbook tone. English goes in examples.
- Be short. Most answers: 2 to 6 sentences, or a few bullets. Go longer only if they ask for a full explanation.
- Ground the answer in their own data when it helps: quote their real mistakes ("você disse 'the company use'"), their weak sounds, their words.
- Give examples about their life and work (data, satellites, agroforestry, travel), not generic textbook ones.
- Markdown: **bold** for the key form, *italics* for English examples, "- " bullets. No headings, no tables.
- If they write in English, answer in Portuguese anyway, but first give a corrected version of what they wrote if it had errors.
- If they ask something the app can't do, say so plainly.

# Actions
You can change the app. Every action shows up under your reply with an undo button, so act when it helps, without asking first, but never more than 4 per reply.
- criar_cartao: a flashcard (front, back, optional note). Create cards when you teach something worth remembering or when they ask. One fact per card. Usual shape: front in Portuguese ("Como se diz: prazo final") or an English sentence with ____; back in English. Keep both short.
- guardar_palavra: a vocabulary item (word, meaning_pt, example). It also becomes a flashcard. Use it for a word or expression they asked about.
- frase_treino: one practice sentence for a sound drill (tag, text). 6 to 12 words, about their life, with 2 or more words that have the sound. The app checks the sound with a pronunciation dictionary and drops sentences without it.
- som_da_vez: change the "sound of the moment" shown on the Today screen (tag). Empty tag returns to automatic. Only when they ask.
- meta_semana: weekly target, sessions per week from 1 to 7 (value). Only when they ask.
- objetivo: their goal with English, in their words (text). Only when they ask.
- abrir: suggest one screen to open now (value: the route, text: a short button label in Portuguese). Screens: {screens}
Fill every field of an action; use "" for the fields that action doesn't use.

# Sound tags
{tags}"""


def _context() -> str:
    profile = plan.pron_profile()
    weak = [s for s in profile if s["status"] in ("treinar", "atenção")]
    ok = [s for s in profile if s["status"] == "ok"]
    lines = ["# About the student (their own notes, in Portuguese)", tutor._profile_text(), ""]
    lines.append("# Pronunciation (phoneme detector, last 60 days)")
    for s in weak:
        lines.append(f"- needs work: {s['label']} ({s['symbol']}, tag {s['tag']}): different from expected "
                     f"{s['off']} of {s['n']} times ({s['rate']:.0%}); natives {s['native']:.0%}")
    if ok:
        lines.append("- fine, like natives: " + ", ".join(s["label"] for s in ok))
    words = [w for w in db.problem_words("2000-01-01", limit=8)]
    if words:
        lines.append("- words where a sound came out wrong: " + ", ".join(f"{w['word']} ({pron.LABEL[w['tag']]}, {w['misses']}x)"
                                                                     for w in words))
    focus = plan.focus_sound(profile)
    if focus:
        lines.append(f"- sound of the moment on the Today screen: {focus['label']} (tag {focus['tag']}"
                     f"{', chosen by the student' if focus.get('chosen') else ', automatic'})")
    lst = listen.stats()["sounds"]
    heard = [s for s in lst if s["n"]]
    if heard:
        lines.append("- listening drill (pick the word you heard): " + ", ".join(
            f"{s['label']} {s['ok']}/{s['n']}" for s in heard))
    lines += ["", "# Grammar notebook (patterns counted in their conversations)"]
    for p in plan.grammar_profile()[:10]:
        lines.append(f"- {p['pattern']} ({p['label']}): {p['count']}x{', due for review' if p['due'] else ''}")
    lines += ["", "# Their latest corrected sentences"]
    for m in db.recent_mistakes(10):
        lines.append(f'- "{m["original"]}" -> "{m["better"]}"')
    nb = db.notebook()["words"][:12]
    if nb:
        lines += ["", "# Words they saved", ", ".join(f"{w['word']} ({w['meaning_pt']})" for w in nb)]
    s = deck.summary()
    settings = db.get_settings()
    lines += ["", "# Study state",
              f"- flashcards: {s['counts']['total']} in the deck, {s['due']} due now, {s['new']} new available today",
              f"- weekly target: {settings['weekly_target']} sessions; this week so far: {plan.week()['done']}",
              f"- goal: {settings.get('goal') or '(none written)'}",
              "- conversation scenarios (id: title): " + "; ".join(f"{k}: {v['title']}" for k, v in tutor.scenarios().items())]
    return "\n".join(lines)


def _history(thread: int) -> str:
    out = []
    for m in db.ask_messages(thread, limit=16):
        if m["role"] == "user":
            out.append(f"Student: {m['text']}")
        else:
            done = [a["label"] for a in m["actions"] if not a.get("undone") and a["type"] != "abrir"]
            out.append(f"Teacher: {m['text']}" + (f"\n[actions taken: {'; '.join(done)}]" if done else ""))
    return "\n\n".join(out) or "(this is the first message)"


def _set(key: str, value: str) -> dict:
    prev = db.get_settings().get(key, "")
    db.set_setting(key, value)
    return {"setting": key, "value": prev}


def _apply(a: dict) -> dict | None:
    """Faz a ação e devolve o registro para a tela, com o que precisa para desfazer."""
    t = a.get("type")
    g = lambda k: str(a.get(k) or "").strip()
    if t == "criar_cartao" and g("front") and g("back"):
        cid = deck.create("livre", g("front"), g("back"), note=g("note"), source="perguntar")
        return {"type": t, "label": f"Cartão: {g('front')} → {g('back')}", "undo": {"card": cid}}
    if t == "guardar_palavra" and g("word") and g("meaning_pt"):
        wid = db.add_word(g("word")[:80], g("meaning_pt")[:200], g("example")[:300])
        deck.sync()
        return {"type": t, "label": f"Palavra guardada: {g('word')} ({g('meaning_pt')})", "undo": {"word": wid}}
    if t == "frase_treino" and g("tag") in drills.ITEMS and g("text"):
        targets = drills.sound_words(g("tag"), g("text"))
        if not targets:
            return None
        did = db.add_drill_item(g("tag"), g("text")[:200], targets)
        return {"type": t, "label": f"No treino do {pron.SYMBOL[g('tag')]}: {g('text')}", "undo": {"drill": did}}
    if t == "som_da_vez" and (g("tag") in pron.LABEL or not g("tag")):
        undo = _set("focus_tag", g("tag"))
        label = f"Som da vez: {pron.LABEL[g('tag')]}" if g("tag") else "Som da vez volta a ser automático"
        return {"type": t, "label": label, "undo": undo}
    if t == "meta_semana" and g("value").isdigit() and 1 <= int(g("value")) <= 7:
        undo = _set("weekly_target", g("value"))
        return {"type": t, "label": f"Meta: {g('value')} sessões por semana", "undo": undo}
    if t == "objetivo" and g("text"):
        undo = _set("goal", g("text")[:300])
        return {"type": t, "label": f"Objetivo: {g('text')[:300]}", "undo": undo}
    if t == "abrir" and _route_ok(g("value")):
        return {"type": t, "label": g("text") or "Abrir", "href": g("value")}
    return None


def _route_ok(href: str) -> bool:
    parts = href.removeprefix("#/").split("/")
    name, rest = parts[0], parts[1:]
    if name in ("frases", "cartoes", "fale-certo", "leitura", "pronuncia") and not rest:
        return True
    if name in ("treino", "ouvir") and len(rest) == 1:
        return rest[0] in drills.ITEMS or (name == "ouvir" and rest[0] in listen.PAIRS)
    if name == "conversar" and len(rest) == 1:
        return rest[0] in tutor.scenarios()
    return name == "erros" and len(rest) <= 1


def undo(record: dict):
    u = record.get("undo") or {}
    if "card" in u:
        db.delete_card(u["card"])
    elif "word" in u:
        db.delete_word(u["word"])
    elif "drill" in u:
        db.delete_drill_item(u["drill"])
    elif "setting" in u:
        db.set_setting(u["setting"], u["value"])


def reply(thread: int, text: str) -> dict:
    tags = "\n".join(f"- {tag}: {pron.LABEL[tag]} ({pron.SYMBOL[tag]}, as in {pron.EXAMPLE[tag]})" for tag in pron.LABEL)
    system = SYSTEM.format(screens="; ".join(f"{k} ({v})" for k, v in SCREENS.items()), tags=tags)
    prompt = (f"{_context()}\n\n# Conversation so far\n{_history(thread)}\n\n"
              f"# The student's new message\n{text}\n\nWrite your reply.")
    data = llm.complete_json(system, prompt, SCHEMA)
    done = [r for r in (_apply(a) for a in (data.get("actions") or [])[:4]) if r]
    return {"text": str(data.get("reply") or "").strip(), "actions": done}
