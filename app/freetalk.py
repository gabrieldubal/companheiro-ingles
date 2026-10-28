"""Usar livre: uma pergunta feita para puxar a forma que você corrigiu, e você responde falando.

É o teste de que a correção pegou: acertar lendo uma frase pronta não garante acertar falando
à vontade. A pergunta mira um padrão de gramática seu (com o seu erro de exemplo) ou um som
fraco; a resposta é avaliada pelo Claude (gramática) e pelo detector (sons). Acertou o padrão
na fala livre, ele sobe de caixa no caderno; errou de novo, volta para a caixa 1.
"""
from . import db, llm, plan, pron, tutor

_STR = {"type": "string"}
PROMPTS_SCHEMA = {
    "type": "object",
    "properties": {"prompts": {"type": "array", "items": {
        "type": "object",
        "properties": {"id": {"type": "integer"}, "question_en": _STR, "question_pt": _STR, "target": _STR},
        "required": ["id", "question_en", "question_pt", "target"],
        "additionalProperties": False,
    }}},
    "required": ["prompts"],
    "additionalProperties": False,
}
EVAL_SCHEMA = {
    "type": "object",
    "properties": {
        "used_target": {"type": "boolean"},
        "target_ok": {"type": "boolean"},
        "verdict_pt": _STR,
        "better": _STR,
        "corrections": tutor.TURN_SCHEMA["properties"]["corrections"],
        "pattern_counts": tutor.TURN_SCHEMA["properties"]["pattern_counts"],
    },
    "required": ["used_target", "target_ok", "verdict_pt", "better", "corrections", "pattern_counts"],
    "additionalProperties": False,
}


def _targets(n: int = 4) -> list[dict]:
    """Os padrões na hora de revisar (com o seu erro de exemplo) e o som fraco que mais pesa."""
    out = []
    for p in plan.grammar_profile():
        ex = next(iter(p.get("examples") or []), None)
        if ex and ex.get("better"):
            out.append({"kind": "padrao", "ref": p["pattern"], "label": p["label"], "example": ex})
        if len(out) >= n - 1:
            break
    weak = [s for s in plan.pron_profile() if s["status"] in ("treinar", "atenção") and s["rate"] >= 0.05]
    focus = plan.focus_sound()
    tag = focus["tag"] if focus else (weak[0]["tag"] if weak else None)
    if tag:
        out.append({"kind": "som", "ref": tag, "label": pron.LABEL.get(tag, tag), "example": pron.EXAMPLE.get(tag, "")})
    return out


def _describe(t: dict) -> str:
    if t["kind"] == "padrao":
        e = t["example"]
        return (f'grammar pattern "{t["ref"]}". Their past mistake: "{e["original"]}" -> "{e["better"]}". The answer '
                "should naturally need this structure")
    return (f'pronunciation: the sound {pron.SYMBOL.get(t["ref"], "")} ({t["label"]}, as in {t["example"]}). The answer '
            "should naturally contain several common words with this sound")


def make_prompts(targets: list[dict]) -> list[dict]:
    if not targets:
        return []
    system = ("You write speaking prompts for a Brazilian learner of English (around B1). Each prompt is one open "
              "question they answer aloud in 20 to 40 seconds, about their own life and work.")
    prompt = (f"Learner profile (Portuguese):\n{tutor._profile_text()}\n\nTargets:\n"
              + "\n".join(f"{i}. {_describe(t)}" for i, t in enumerate(targets)) + "\n\n"
              "For each target, write one prompt with the same id. question_en: a simple, natural question in English "
              "that makes the target structure or sound come up without naming it (for the past simple, ask about a "
              "past event; for 'on the final day', ask about the last day of a trip; for the th sound, ask something "
              "whose answer needs think, three, thing, month). question_pt: the question in Brazilian Portuguese. "
              "target: in English, a few words saying what a good answer contains (e.g. 'past simple: went, visited').")
    data = llm.complete_json(system, prompt, PROMPTS_SCHEMA)
    made = []
    for p in data.get("prompts") or []:
        i = p.get("id")
        if isinstance(i, int) and 0 <= i < len(targets) and str(p.get("question_en") or "").strip():
            t = targets[i]
            pid = db.add_prompt(t["kind"], t["ref"], p["question_en"].strip(), str(p.get("question_pt") or "").strip(),
                                str(p.get("target") or "").strip())
            made.append(db.get_prompt(pid))
    return made


def queue(kind: str | None = None, ref: str | None = None) -> list[dict]:
    """Perguntas abertas; se faltarem, pede novas ao Claude (uns 10 segundos)."""
    if kind:
        rows = db.open_prompts(limit=3, kind=kind, ref=ref)
        if not rows:
            t = next((x for x in _targets(8) if x["kind"] == kind and x["ref"] == ref), None)
            if not t and kind == "som":
                t = {"kind": "som", "ref": ref, "label": pron.LABEL.get(ref, ref), "example": pron.EXAMPLE.get(ref, "")}
            if not t and kind == "padrao":
                ex = next(iter(db.notebook_examples(ref)), None)
                t = {"kind": "padrao", "ref": ref, "label": tutor.PATTERN_PT.get(ref, ref), "example": ex} if ex else None
            rows = make_prompts([t]) if t else []
        return [_public(r) for r in rows]
    rows = db.open_prompts(limit=6)
    if len(rows) < 2:
        rows += make_prompts(_targets())
    return [_public(r) for r in rows]


def _public(r: dict) -> dict:
    label = pron.LABEL.get(r["ref"]) if r["kind"] == "som" else tutor.PATTERN_PT.get(r["ref"], r["ref"])
    return {**r, "label": label, "symbol": pron.SYMBOL.get(r["ref"], "") if r["kind"] == "som" else ""}


def evaluate(p: dict, text: str, unsure: list[str]) -> dict:
    system = ("You are an English teacher checking a Brazilian learner's spoken answer. It comes from speech "
              "recognition: ignore capitalization, punctuation and fillers, and never correct likely transcription "
              "artifacts. Write every *_pt field in Brazilian Portuguese, direct and warm, no flattery.")
    focus = (f'The target is the grammar pattern "{p["ref"]}" ({tutor.PATTERN_PT.get(p["ref"], p["ref"])}).'
             if p["kind"] == "padrao" else
             f"The target is pronunciation of {pron.LABEL.get(p['ref'], p['ref'])}: the app checks the sounds itself, "
             "so judge only content and grammar here, and set used_target and target_ok to true.")
    prompt = (
        f'Question: "{p["question_en"]}"\nWhat a good answer contains: {p["target"]}\n{focus}\n\n'
        f'The learner said (speech recognition): "{text}"\n'
        + (f"Words the recognizer was unsure about (maybe pronunciation, not grammar): {', '.join(unsure)}\n" if unsure else "")
        + "\nReturn:\n"
        "- used_target: did they use (or try to use) the target structure?\n"
        "- target_ok: did they use it correctly every time they used it?\n"
        "- verdict_pt: one or two sentences: did the corrected form show up in free speech, and the one thing to "
        "watch next.\n"
        "- better: their whole answer as a native speaker would say it, keeping their ideas and most of their words.\n"
        "- corrections: up to 3 cards, the most important errors first, same rules as conversation cards: original "
        "(exact fragment), better, explanation_pt, pattern (closest tag from this list, copied exactly: "
        + "; ".join(tutor.PATTERNS) + "), meaning_pt (what they meant, short, in Portuguese).\n"
        "- pattern_counts: the full error count of the answer by pattern, with one example each."
    )
    data = llm.complete_json(system, prompt, EVAL_SCHEMA)
    turn = tutor._clean_turn({**data, "reply": "", "reply_pt": "", "new_words": [], "good_uses": []}, 3)
    return {"used_target": bool(data.get("used_target")), "target_ok": bool(data.get("target_ok")),
            "verdict_pt": str(data.get("verdict_pt") or "").strip(), "better": str(data.get("better") or "").strip(),
            "corrections": turn["corrections"], "pattern_counts": turn["pattern_counts"]}


def apply(p: dict, ev: dict, text: str, rid: int):
    """A fala livre entra no caderno como uma resposta de conversa, e mexe na caixa do padrão-alvo."""
    good = [p["ref"]] if p["kind"] == "padrao" and ev["used_target"] and ev["target_ok"] else []
    db.record_feedback(None, ev["corrections"], ev["pattern_counts"], good, [])
    if p["kind"] == "padrao" and ev["used_target"]:
        db.add_practice("usar", p["ref"], None, p["target"], text, ev["target_ok"], rid)
        if not ev["target_ok"]:
            db.practice_result(p["ref"], False)
    db.answer_prompt(p["id"])
