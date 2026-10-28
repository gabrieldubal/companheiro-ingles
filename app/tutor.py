"""Cenários, níveis e prompts do tutor."""
import json
import re

from . import config, db, llm

# A escala é a mesma da pergunta da mentoria.
LEVELS = [
    {"value": 1, "label": "Nível 1: travo em frase simples"},
    {"value": 2, "label": "Nível 2: me viro devagar, com pausas"},
    {"value": 2.5, "label": "Entre o 2 e o 3"},
    {"value": 3, "label": "Nível 3: converso sobre o trabalho, com esforço"},
    {"value": 4, "label": "Nível 4: faria uma entrevista técnica amanhã"},
]
DEFAULT_LEVEL = 2.5

LEVEL_SCALE = (
    "1 = gets stuck on simple sentences; 2 = manages slowly, with many pauses; "
    "3 = talks about their work, with effort; 4 = could do a technical job interview in English tomorrow."
)


def level_profile(level: float) -> dict:
    if level <= 1.5:
        return {
            "cefr": "A2", "max_corrections": 1, "tts_rate": 0.8,
            "text": "The student is a beginner (around A2). Use very short sentences (at most 12 words each), "
                    "only very common words, and mostly present and past simple. Ask one simple question at a time. "
                    "If they seem stuck, offer two short options they can choose from. Keep your reply under 30 words.",
        }
    if level <= 2.2:
        return {
            "cefr": "B1-", "max_corrections": 2, "tts_rate": 0.85,
            "text": "The student is a lower-intermediate speaker (around B1-). They understand slow, clear English "
                    "and speak with pauses. Use short, clear sentences and common vocabulary. Avoid idioms and phrasal "
                    "verbs unless the meaning is obvious. One question per turn. Keep your reply under 40 words.",
        }
    if level <= 2.7:
        return {
            "cefr": "B1", "max_corrections": 2, "tts_rate": 0.9,
            "text": "The student is between lower-intermediate and intermediate (around B1). They can talk about "
                    "their work with effort and pauses. Use clear sentences with everyday and work vocabulary, and at "
                    "most one idiom or phrasal verb per turn. Encourage longer answers with open questions "
                    "(why, how, tell me about). Keep your reply under 50 words.",
        }
    if level <= 3.5:
        return {
            "cefr": "B1+/B2", "max_corrections": 3, "tts_rate": 0.95,
            "text": "The student is intermediate (around B1+/B2). Speak naturally but clearly. Push for longer, more "
                    "precise answers with follow-up questions, and use useful collocations. Keep your reply under 60 words.",
        }
    return {
        "cefr": "B2+/C1", "max_corrections": 3, "tts_rate": 1.0,
        "text": "The student is upper-intermediate to advanced (B2+/C1). Use natural speed and vocabulary, idioms are "
                "fine. Challenge them with demanding follow-up questions. Keep your reply under 70 words.",
    }


# Cenários que servem para qualquer pessoa. Os de cada um (os seus, ou os que a tela de boas-vindas
# gera a partir do perfil) ficam em data/cenarios.json e aparecem primeiro.
BASE_SCENARIOS = {
    "livre": {
        "title": "Conversa livre",
        "subtitle": "Seu dia, seu trabalho, o que você quiser",
        "role": "You are Sam, a friendly person from Canada the student met online. Chat naturally about their day, "
                "work or studies, plans and interests. Share small things about yourself too, like a real person "
                "would, so it doesn't feel like an interview.",
    },
    "viagem": {
        "title": "Numa viagem",
        "subtitle": "Aeroporto, hotel, restaurante, pedir informação",
        "role": "You play the people the student meets on a trip abroad, one situation at a time: an airline agent at "
                "check-in, a hotel receptionist, a waiter, a stranger they ask for directions. Say who you are at the "
                "start of each situation in a few words. Keep it realistic: small problems happen (a delayed flight, a "
                "wrong booking, a dish that isn't available) and the student has to sort them out in English. After "
                "4 or 5 exchanges, move to a new situation.",
    },
    "trabalho": {
        "title": "Reunião de trabalho",
        "subtitle": "Explicar o que você faz para um colega estrangeiro",
        "role": "You are Jordan, a new colleague from the international team in a video call with the student. Ask "
                "them to explain their work or studies: what they do day to day, a problem they solved recently, what "
                "is blocking them, and what comes next. Ask follow-up questions like a curious coworker who wants to "
                "understand the details. Use the student's profile to make the questions specific.",
    },
    "entrevista": {
        "title": "Entrevista de emprego",
        "subtitle": "Primeira conversa com um recrutador",
        "role": "You are Alex, a recruiter at an international company doing a first screening call for a role in the "
                "student's field (see their profile). Ask classic questions one at a time: tell me about yourself, why "
                "you are looking for a new role, a project you are proud of, a time you had too many tasks at once, "
                "strengths and weaknesses, and salary expectations. React briefly and realistically, like a recruiter.",
    },
    "ideias": {
        "title": "Conversa sobre ideias",
        "subtitle": "Um livro, um filme, uma notícia, um assunto seu",
        "role": "You are Ingrid, a thoughtful friend who loves ideas. Ask what the student has been reading, watching or "
                "thinking about lately (use their profile and interests). Ask for their opinion, sometimes disagree "
                "respectfully, and connect the ideas to their life. A conversation between equals.",
    },
    "diagnostico": {
        "title": "Diagnóstico de nível",
        "subtitle": "8 perguntas que vão ficando mais difíceis",
        "role": "You are a warm, experienced English examiner running a short, informal speaking assessment. Ask "
                "about 8 questions in total, one per turn, gradually harder: simple personal questions, then "
                "describing their work, then a past experience, then hypotheticals ('What would you do if...'), then "
                "opinions they must justify. Don't teach during the assessment: keep your replies short and neutral "
                "(corrections still go in the corrections field). After about 8 questions, tell the student they "
                "can end the session to see the result.",
    },
}



def custom_scenarios() -> dict:
    """Os cenários da pessoa (data/cenarios.json): os seus, ou os gerados a partir do perfil."""
    try:
        items = json.loads(config.SCENARIOS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    out = {}
    for it in items if isinstance(items, list) else []:
        if all(str(it.get(k) or "").strip() for k in ("id", "title", "role")):
            out[it["id"]] = {"title": it["title"], "subtitle": it.get("subtitle", ""), "role": it["role"], "custom": True}
    return out


def scenarios() -> dict:
    """Os da pessoa primeiro, depois os genéricos."""
    return {**custom_scenarios(), **{k: v for k, v in BASE_SCENARIOS.items()}}


# Etiquetas fixas para o caderno conseguir contar o mesmo erro ao longo das semanas.
PATTERNS = [
    "past simple (finished actions)", "present perfect vs past simple", "third person -s",
    "do/does/did in questions and negatives", "question word order", "articles (a/an/the)",
    "no article for general ideas", "prepositions of time and place (in/on/at)", "other prepositions",
    "false friend", "word choice / collocation", "make vs do", "say vs tell", "countable vs uncountable",
    "plural nouns", "adjective position and order", "missing subject (it/there)", "there is/are vs have",
    "verb + -ing or to-infinitive", "modal verbs", "future (will / going to)",
    "comparatives and superlatives", "conditionals", "pronouns", "word order", "verb tense (other)",
    "Portuguese word",
    # Vistos no Diagnóstico de 26/10:
    "repeated subject or extra it's",  # "a company that it's focused" (o "é que" do português)
    "run-on sentence",  # frase que emenda várias ideias sem ponto final
    "data science vs data scientist",  # a área vs a pessoa
]
_PATTERN_BY_KEY = {p.lower(): p for p in PATTERNS}

# Como cada etiqueta aparece para você na tela.
PATTERN_PT = {
    "past simple (finished actions)": "passado simples (ação terminada)",
    "present perfect vs past simple": "present perfect ou passado simples",
    "third person -s": "terceira pessoa: o -s do verbo",
    "do/does/did in questions and negatives": "do, does e did na pergunta e na negação",
    "question word order": "ordem das palavras na pergunta",
    "articles (a/an/the)": "artigos: a, an, the",
    "no article for general ideas": "sem artigo em ideia geral",
    "prepositions of time and place (in/on/at)": "in, on e at",
    "other prepositions": "outras preposições",
    "false friend": "falso cognato",
    "word choice / collocation": "escolha de palavra",
    "make vs do": "make ou do",
    "say vs tell": "say ou tell",
    "countable vs uncountable": "contável e incontável",
    "plural nouns": "plural",
    "adjective position and order": "lugar do adjetivo",
    "missing subject (it/there)": "sujeito que falta: it, there",
    "there is/are vs have": "there is/are no lugar de have",
    "verb + -ing or to-infinitive": "verbo + -ing ou to",
    "modal verbs": "verbos modais",
    "future (will / going to)": "futuro: will, going to",
    "comparatives and superlatives": "comparativo e superlativo",
    "conditionals": "condicionais",
    "pronouns": "pronomes",
    "word order": "ordem das palavras",
    "verb tense (other)": "tempo verbal",
    "Portuguese word": "palavra em português",
    "repeated subject or extra it's": "sujeito repetido, it's sobrando",
    "run-on sentence": "frase sem fim",
    "data science vs data scientist": "data science ou data scientist",
}

_STR = {"type": "string"}
TURN_SCHEMA = {
    "type": "object",
    "properties": {
        "reply": _STR,
        "reply_pt": _STR,
        "corrections": {"type": "array", "items": {
            "type": "object",
            "properties": {"original": _STR, "better": _STR, "explanation_pt": _STR, "pattern": _STR, "meaning_pt": _STR},
            "required": ["original", "better", "explanation_pt", "pattern", "meaning_pt"],
            "additionalProperties": False,
        }},
        "new_words": {"type": "array", "items": {
            "type": "object",
            "properties": {"word": _STR, "meaning_pt": _STR, "example": _STR},
            "required": ["word", "meaning_pt", "example"],
            "additionalProperties": False,
        }},
        "pattern_counts": {"type": "array", "items": {
            "type": "object",
            "properties": {"pattern": _STR, "count": {"type": "integer"}, "original": _STR, "better": _STR,
                           "meaning_pt": _STR},
            "required": ["pattern", "count", "original", "better", "meaning_pt"],
            "additionalProperties": False,
        }},
        "good_uses": {"type": "array", "items": _STR},
    },
    "required": ["reply", "reply_pt", "corrections", "new_words", "pattern_counts", "good_uses"],
    "additionalProperties": False,
}

SUMMARY_SCHEMA = {
    "type": "object",
    "properties": {
        "summary_pt": _STR,
        "went_well_pt": {"type": "array", "items": _STR},
        "focus_pt": _STR,
        "best_sentences": {"type": "array", "items": _STR},
        "cefr_estimate": _STR,
        "scale_estimate": {"type": "number"},
        "level_comment_pt": _STR,
    },
    "required": ["summary_pt", "went_well_pt", "focus_pt", "best_sentences",
                 "cefr_estimate", "scale_estimate", "level_comment_pt"],
    "additionalProperties": False,
}

_SYSTEM = """You are an English conversation partner for a Brazilian Portuguese speaker who practices spoken English on their phone.

# Your role in this conversation
{role}

# About the student (their own notes, in Portuguese)
{profile}

# The student's level
{level}

# How the conversation works
- The student's messages come from speech recognition. Ignore capitalization, punctuation and filler words (um, uh), and never correct something that is probably a transcription artifact.
- Talk like a real person in your role: react to what they said first, then keep the conversation going. Most turns end with one question.
- Never explain grammar in "reply". Corrections go only in the "corrections" field, which the app shows separately as cards. You may naturally use the correct form in your reply without pointing it out.
- If the student uses Portuguese or asks how to say something, help in the corrections field (pattern "Portuguese word") and keep the conversation going in English.
- "reply" is English only. "reply_pt" is a natural Brazilian Portuguese translation of your reply, shown only if the student taps "traduzir".

# Corrections
- Look only at the student's latest message.
- Each message comes with the number of correction cards allowed for it (longer answers get more). Choose the cards in this order: first errors that repeat inside this message, then errors that match the recurring patterns below, then errors that change the meaning or sound clearly unnatural. Skip tiny slips when there are bigger errors.
- If the message is fine, return an empty list. Never invent errors.
- "original": the exact fragment the student said. "better": the same fragment as a native speaker would say it. "explanation_pt": one short sentence in Brazilian Portuguese explaining why, written like a friend, not a textbook. "meaning_pt": what the student was trying to say with that fragment, as a short natural Brazilian Portuguese phrase (the idea, not a word-by-word translation of the mistake). Weeks later the app shows "Você queria dizer: ..." so the student knows what to say when they practice the correct version.
- "pattern": the closest tag from this list, copied exactly: {patterns}. Only if none fits, write a new short tag in English.
- Very long sentences that chain many ideas with "like", "and", "so" and no full stop count as "run-on sentence". For that card, "better" splits the fragment into short sentences.

# Pattern counts
"pattern_counts" is the full error count of the student's latest message, including the errors you did not turn into cards. One entry per pattern, with how many times it occurred, plus one short example ("original", "better" and "meaning_pt", as in the cards) from this message. Use the same tags as above. Leave out likely transcription artifacts. This is how the app learns which errors repeat the most, so count carefully: for example, every "the company use" or "AI need" counts toward "third person -s".

# Recurring patterns to practice
{recurring}

# New words
Optionally put one useful word or expression in "new_words", only when it fits naturally with what the student was trying to say. Leave it empty in most turns.

# Good uses
If the student correctly used one of the recurring patterns above, put its exact tag in "good_uses"."""


def scenarios_public() -> list:
    return [{"id": k, "title": v["title"], "subtitle": v["subtitle"], "custom": bool(v.get("custom"))}
            for k, v in scenarios().items()]


def recurring_now() -> list:
    return db.due_patterns(limit=3)


def _recurring_text(recurring: list) -> str:
    if not recurring:
        return "None due for review right now. Don't force any structure."
    lines = [
        f'- {r["pattern"]} (seen {r["count"]}x). Last example: "{r.get("original", "")}" -> "{r.get("better", "")}"'
        for r in recurring
    ]
    return "\n".join(lines) + (
        "\nCreate natural chances for the student to use these structures (for example, ask about the past "
        "if they struggle with the past simple). Don't tell them you are doing it."
    )


def _profile_text() -> str:
    try:
        text = config.PROFILE.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        text = "(no profile)"
    goal = db.get_settings().get("goal", "").strip()
    if goal:  # o objetivo escrito em Ajustes puxa a conversa para ele
        text += (f"\n\nThe student's current goal with English (in their words): {goal}\n"
                 "When it fits your role, steer the conversation toward situations that prepare for this goal.")
    return text


def system_prompt(session: dict) -> str:
    # Igual durante toda a sessão (o que muda por mensagem vai no prompt do turno).
    return _SYSTEM.format(
        role=scenarios().get(session["scenario"], BASE_SCENARIOS["livre"])["role"],
        profile=_profile_text(),
        level=level_profile(session["level"])["text"],
        patterns="; ".join(PATTERNS),
        recurring=_recurring_text(session["recurring"]),
    )


def card_limit(level: float, text: str) -> int:
    """Resposta longa ganha mais cartões: com 2 fixos, o erro mais frequente sumia."""
    n = len(text.split())
    extra = (n > 120) + (n > 250)
    return min(level_profile(level)["max_corrections"] + extra, 4)


def _transcript(turns: list) -> str:
    lines = [f'{"Tutor" if t["role"] == "tutor" else "Student"}: {t["text"]}' for t in turns[-40:]]
    return "\n".join(lines) if lines else "(nothing yet)"


def _tag(raw) -> str:
    tag = str(raw or "").strip()
    return _PATTERN_BY_KEY.get(tag.lower(), tag.lower() or "word choice / collocation")


def _clean_turn(data: dict, max_corrections: int) -> dict:
    corrections = []
    for c in data.get("corrections", [])[:max_corrections]:
        c["pattern"] = _tag(c.get("pattern"))
        if c.get("original", "").strip() and c.get("better", "").strip():
            corrections.append(c)
    # Soma por etiqueta e garante que todo cartão conta pelo menos 1.
    counts = {}
    for pc in data.get("pattern_counts", []):
        tag = _tag(pc.get("pattern"))
        n = max(1, min(int(pc.get("count") or 1), 50))
        entry = counts.setdefault(tag, {"pattern": tag, "count": 0, "original": pc.get("original", ""),
                                        "better": pc.get("better", ""), "meaning_pt": pc.get("meaning_pt", "")})
        entry["count"] += n
    for c in corrections:
        counts.setdefault(c["pattern"], {"pattern": c["pattern"], "count": 1, "original": c["original"],
                                         "better": c["better"], "meaning_pt": c.get("meaning_pt", "")})
    return {
        "reply": str(data.get("reply", "")).strip(),
        "reply_pt": str(data.get("reply_pt", "")).strip(),
        "corrections": corrections,
        "pattern_counts": sorted(counts.values(), key=lambda x: -x["count"]),
        "new_words": data.get("new_words", [])[:1],
        "good_uses": [_tag(g) for g in data.get("good_uses", [])],
    }


SCENARIOS_SCHEMA = {
    "type": "object",
    "properties": {"scenarios": {"type": "array", "items": {
        "type": "object",
        "properties": {"title": _STR, "subtitle": _STR, "role": _STR},
        "required": ["title", "subtitle", "role"],
        "additionalProperties": False,
    }}},
    "required": ["scenarios"],
    "additionalProperties": False,
}


def generate_scenarios(n: int = 4) -> list[dict]:
    """Cenários de conversa feitos para a pessoa, a partir do perfil (a tela de boas-vindas chama)."""
    system = ("You design speaking-practice scenarios for a Brazilian learner of English. Each scenario is a role "
              "the conversation partner plays, written in English as an instruction to that partner.")
    examples = "\n".join(f'- {v["title"]}: {v["role"]}' for k, v in BASE_SCENARIOS.items() if k in ("trabalho", "entrevista"))
    prompt = (f"Learner profile (Portuguese):\n{_profile_text()}\n\n"
              f"Write {n} scenarios made for this person: their real goal with English, their work or studies, a trip "
              "or situation they mentioned, and one topic they like talking about. Each one: title (Brazilian "
              "Portuguese, 2 to 5 words), subtitle (Portuguese, one short line), role (English, 2 to 4 sentences: who "
              "the partner is, what they ask about, how they behave; one question at a time). Don't repeat these "
              f"generic ones the app already has: casual chat, travel situations, explaining your work, a recruiter "
              f"screening, talking about ideas.\nExamples of the role style:\n{examples}")
    data = llm.complete_json(system, prompt, SCENARIOS_SCHEMA)
    made = []
    for i, sc in enumerate((data.get("scenarios") or [])[:n]):
        title, role = str(sc.get("title") or "").strip(), str(sc.get("role") or "").strip()
        if title and role:
            slug = re.sub(r"[^a-z0-9]+", "-", title.lower().encode("ascii", "ignore").decode()).strip("-")[:30]
            made.append({"id": f"meu-{i + 1}-{slug or 'cenario'}", "title": title[:60],
                         "subtitle": str(sc.get("subtitle") or "").strip()[:90], "role": role[:900], "source": "gerado"})
    # Os gerados substituem os gerados antes; os que a pessoa já tinha ficam.
    try:
        old = json.loads(config.SCENARIOS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        old = []
    keep = [s for s in old if isinstance(s, dict) and s.get("source") != "gerado"]
    config.SCENARIOS_FILE.write_text(json.dumps(keep + made, ensure_ascii=False, indent=2), encoding="utf-8")
    return made


MEANINGS_SCHEMA = {
    "type": "object",
    "properties": {"meanings": {"type": "array", "items": {
        "type": "object",
        "properties": {"id": {"type": "integer"}, "meaning_pt": _STR},
        "required": ["id", "meaning_pt"],
        "additionalProperties": False,
    }}},
    "required": ["meanings"],
    "additionalProperties": False,
}


def backfill_meanings():
    """Para os erros de antes deste campo: o que você queria dizer, tirado da frase em volta."""
    if config.llm_backend() == "demo":
        return
    todo = db.mistakes_without_meaning(limit=60)
    lines = []
    for m in todo:
        ctx = db.mistake_context(m["session_id"], m["original"]) or {}
        around = " ".join(x for x in (ctx.get("before"), ctx.get("match"), ctx.get("after")) if x) or m["original"]
        lines.append(f'{m["id"]}. Context: "...{around}..." | They said: "{m["original"]}" | Correct: "{m["better"]}"')
    if not lines:
        return
    prompt = ("For each item, write meaning_pt: what the student was trying to say with that fragment, as a short "
              "natural Brazilian Portuguese phrase (the idea, not a word-by-word translation of the mistake). The app "
              "shows it as 'Você queria dizer: ...' when the student practices saying the correct version.\n\n"
              + "\n".join(lines))
    system = "You help a Brazilian student review their own English mistakes. Write meaning_pt in natural Brazilian Portuguese."
    try:
        data = llm.complete_json(system, prompt, MEANINGS_SCHEMA)
    except llm.LLMError as e:
        print(f"[tutor] sentidos dos erros antigos ficaram para depois: {e}")
        return
    ids = {m["id"] for m in todo}
    for it in data.get("meanings", []):
        if it.get("id") in ids and str(it.get("meaning_pt") or "").strip():
            db.set_mistake_meaning(it["id"], it["meaning_pt"].strip())


def opening(session: dict) -> dict:
    prompt = (
        "Start the conversation now with your first message, in your role. Greet the student and ask your "
        "first question. There is no student message yet, so corrections, new_words, pattern_counts and "
        "good_uses must be empty."
    )
    data = llm.complete_json(system_prompt(session), prompt, TURN_SCHEMA)
    data["pattern_counts"] = []
    turn = _clean_turn(data, 0)
    turn["new_words"] = []
    return turn


def respond(session: dict, turns: list, text: str, unsure: list | None = None) -> dict:
    limit = card_limit(session["level"], text)
    unsure_line = ""
    if unsure:
        unsure_line = (
            "\nThe speech recognizer was unsure about these words, so they may be mis-transcribed "
            f"(possibly a pronunciation issue): {', '.join(unsure)}. Don't correct them as grammar or vocabulary.\n"
        )
    prompt = (
        f"Conversation so far:\n{_transcript(turns)}\n\n"
        f'The student\'s latest message (from speech recognition): "{text}"\n'
        f"{unsure_line}\n"
        f"Correction cards allowed for this message: at most {limit}.\n\n"
        "Write your next turn."
    )
    data = llm.complete_json(system_prompt(session), prompt, TURN_SCHEMA)
    return _clean_turn(data, limit)


def summarize(session: dict, turns: list, mistakes: list) -> dict:
    student_turns = [t for t in turns if t["role"] == "student"]
    if len(student_turns) < 2:
        return {
            "summary_pt": "Conversa curta demais para um resumo. Na próxima, tenta ir até umas 6 respostas.",
            "went_well_pt": [], "focus_pt": "", "best_sentences": [],
            "cefr_estimate": "", "scale_estimate": 0, "level_comment_pt": "",
        }
    corrections = "\n".join(
        f'- [{m["pattern"]}] "{m["original"]}" -> "{m["better"]}"' for m in mistakes
    ) or "(none)"
    totals = {}
    for t in student_turns:
        for pc in (t["data"] or {}).get("pattern_counts", []):
            totals[pc["pattern"]] = totals.get(pc["pattern"], 0) + pc["count"]
    if totals:
        ranked = sorted(totals.items(), key=lambda x: -x[1])
        corrections += "\n\nError counts for the whole conversation (most frequent first):\n" + "\n".join(
            f"- {p}: {n}x" for p, n in ranked
        )
    system = (
        "You are an experienced English teacher reviewing a practice conversation of a Brazilian student. "
        "Write every *_pt field in Brazilian Portuguese: direct and warm, no flattery, no textbook tone."
    )
    prompt = (
        f"Scenario: {scenarios().get(session['scenario'], BASE_SCENARIOS['livre'])['title']}\n\n"
        f"Conversation:\n{_transcript(turns)}\n\n"
        f"Corrections given during the conversation:\n{corrections}\n\n"
        "Return:\n"
        "- summary_pt: 2 or 3 sentences on how the conversation went.\n"
        "- went_well_pt: up to 3 concrete things the student did well.\n"
        "- focus_pt: the ONE thing to practice next, concrete and doable (not 'study grammar').\n"
        "- best_sentences: the 3 most useful things the student tried to say, rewritten as a native speaker "
        "would say them, keeping the student's ideas and words where possible. The student will listen and "
        "repeat them aloud.\n"
        "- cefr_estimate: a rough CEFR level such as 'B1'.\n"
        f"- scale_estimate: the student's own scale, from 1 to 4, decimals allowed. Scale: {LEVEL_SCALE}\n"
        "- level_comment_pt: one sentence explaining the estimate. Say it is rough: one short conversation, "
        "judged from text only, without pronunciation."
    )
    return llm.complete_json(system, prompt, SUMMARY_SCHEMA)
