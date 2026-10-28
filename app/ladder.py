"""Escada de correção: para uma palavra em que um som saiu trocado.

Degraus, do mais fácil ao mais difícil:
  1. o som em pares mínimos (think, sink);
  2. palavras curtas com o mesmo som (thin, thick, both);
  3. a sua palavra sozinha;
  4. a sua palavra contra o que ela soou para um nativo (think, sink), se soou como outra palavra;
  5. a frase em que você errou (ou uma frase do banco com a palavra).
Cada degrau sobe com 2 acertos seguidos no som. Vencida a escada, a palavra sai da lista.
"""
import re

from . import db, drills, phrases, pron

PASS_STREAK = 2

# Pares para os sons que o treino não tem em par. No l do fim, o erro do português é trocar
# o l por u: goal vira go. No -ed, o par ensina a regra: só depois de t ou d o -ed vira sílaba.
EXTRA_PAIRS = {
    "dark-l": [("go, goal", ["goal"]), ("row, roll", ["roll"]), ("fee, feel", ["feel"])],
    "ed": [("wanted, walked", ["walked"]), ("needed, cleaned", ["cleaned"]), ("added, played", ["played"])],
}
PAIR_HELP = {
    "dark-l": "Sem o l, goal vira go. Termine a segunda palavra com a ponta da língua no céu da boca, atrás dos dentes.",
    "ed": "Só depois de t ou d o -ed vira sílaba: wanted tem duas, walked tem uma. A segunda palavra do par não ganha vogal.",
}

# Palavras curtas por som. Para ɪ/iː e æ/ɛ, a lista segue a vogal da sua palavra.
WORDS = {
    "th-voiceless": ["thin", "thick", "thing", "three", "both", "math", "month", "health", "earth", "path"],
    "th-voiced": ["this", "that", "they", "then", "mother", "other", "weather", "breathe"],
    "ɪ": ["sit", "bit", "fill", "ship", "live", "big", "this", "fish"],
    "iː": ["seat", "beat", "feel", "sheep", "leave", "green", "these", "need"],
    "æ": ["bad", "man", "had", "cat", "map", "back", "hand", "plan"],
    "ɛ": ["bed", "men", "head", "said", "ten", "pen", "red", "best"],
    "ed": ["worked", "walked", "stopped", "helped", "played", "called", "cleaned", "wanted"],
    "dark-l": ["all", "feel", "school", "people", "small", "full", "well", "cool"],
    "final-s": ["works", "maps", "needs", "plays", "uses", "runs"],
    "aspiration": ["tank", "park", "key", "time", "ten", "pen", "come", "cat"],
    "final-vowel": ["big", "dog", "job", "bad", "stop", "good", "map"],
    "r-initial": ["red", "road", "river", "run", "right", "rain"],
    "h": ["hat", "house", "hand", "hot", "home"],
    "s-cluster": ["school", "study", "stop", "start", "small", "spring"],
    "t-d-palatal": ["city", "pretty", "party", "different", "study"],
    "final-nasal": ["team", "time", "plan", "run", "long", "song"],
}


def _short_words(tag: str, word: str) -> list[str]:
    phones = pron._word(word)["phones"]
    if tag == "i-short-long":
        key = "ɪ" if "ɪ" in phones else "iː"
    elif tag == "ae-e":
        key = "æ" if "æ" in phones else "ɛ"
    else:
        key = tag
    return [w for w in WORDS.get(key, []) if w != word.lower()][:4]


def _is_list(sentence: str) -> bool:
    """'ship, sheep. live, leave.' é uma lista de pares, não uma frase para falar."""
    parts = [p.split() for p in re.split(r"[,.;]", sentence) if p.strip()]
    return len(parts) >= 3 and sum(len(p) == 1 for p in parts) >= 0.6 * len(parts)


def _carrier(word: str, sentence: str | None) -> tuple[str, str]:
    """A frase do último degrau: a sua, se for frase de verdade; senão uma do banco com a palavra."""
    if sentence and 2 <= len(sentence.split()) <= 18 and not _is_list(sentence):
        return sentence, "A frase em que você errou. O detector olha só a sua palavra."
    w = word.lower()
    for p in phrases._pool():
        if w in (re.sub(r"[^a-z']", "", t.lower()) for t in p["text"].split()):
            return p["text"], "Uma frase com a sua palavra. O detector olha só ela."
    # A palavra no fim da frase: é onde o -ed, o l e o s do fim costumam sumir ou ganhar vogal.
    return f"Now I say {word}.", "A palavra no fim de uma frase curta, onde o som costuma escapar."


def steps(tag: str, word: str, heard_as: str | None = None, sentence: str | None = None) -> list[dict]:
    contra = f"{word}, {heard_as}".lower() if heard_as else None  # esse par já tem degrau próprio
    pairs = [{"text": t, "targets": tg} for t, tg in drills.ITEMS.get(tag, [])
             if "," in t and not t.endswith(".") and t.lower() != contra][:3]
    pairs = pairs or [{"text": t, "targets": tg} for t, tg in EXTRA_PAIRS.get(tag, [])]
    out = [
        {"key": "pares", "title": "O som em pares", "items": pairs,
         "help": PAIR_HELP.get(tag, "Ouça o nativo devagar e repita. Os dois lados do par têm que soar diferentes.")},
        {"key": "curtas", "title": "Palavras curtas com o mesmo som",
         "items": [{"text": w, "targets": [w]} for w in _short_words(tag, word)],
         "help": "O mesmo som, em palavras fáceis. Exagere um pouco no começo."},
        {"key": "palavra", "title": f"A sua palavra: {word}", "items": [{"text": word, "targets": [word.lower()]}],
         "help": "Agora a palavra em que o som saiu trocado. Devagar primeiro, depois no ritmo normal."},
    ]
    if heard_as and heard_as.lower() != word.lower():
        out.append({"key": "contra", "title": f"{word} contra {heard_as}",
                    "items": [{"text": f"{word}, {heard_as}", "targets": [word.lower()]}],
                    "help": f"Para um nativo, o seu {word} soou como {heard_as}. Diga os dois e faça a diferença aparecer."})
    text, help_ = _carrier(word, sentence)
    out.append({"key": "frase", "title": "Na frase", "items": [{"text": text, "targets": [word.lower()]}], "help": help_})
    return [s for s in out if s["items"]]


def session(tag: str, word: str, heard_as: str | None, sentence: str | None) -> dict:
    st = db.word_practice(word.lower(), tag)
    attempts = [{**a, "fix": drills.fix_for(a)} for a in db.ladder_attempts(tag, word.lower())]
    return {"tag": tag, "word": word, "heard_as": heard_as, "label": pron.LABEL.get(tag, tag), "symbol": pron.SYMBOL.get(tag, ""),
            "tip": drills.TIPS.get(tag), "steps": steps(tag, word, heard_as, sentence), "state": st,
            "pass_streak": PASS_STREAK, "attempts": attempts, "best": db.best_take(tag, word.lower()),
            "parts": _parts(tag, word, steps(tag, word, heard_as, sentence))}


def _parts(tag: str, word: str, step_list: list[dict]) -> dict:
    """O som em partes para cada palavra-alvo dos degraus: você trava em "think", não em "thick"."""
    words = [word.lower()] + [t for s in step_list for it in s["items"] for t in it["targets"]]
    return {w: drills.parts(tag, w) for w in dict.fromkeys(words)}


def record(tag: str, word: str, step_count: int, ok: bool) -> dict:
    """Atualiza o degrau: 2 acertos seguidos sobem, erro zera a sequência."""
    st = db.word_practice(word.lower(), tag)
    advanced = mastered = False
    if ok:
        st["streak"] += 1
        if st["streak"] >= PASS_STREAK:
            st["step"] += 1
            st["streak"] = 0
            st["fails"] = 0
            advanced = True
            if st["step"] >= step_count:
                mastered = True
    else:
        st["streak"] = 0
        st["fails"] += 1
    db.save_word_practice(word.lower(), tag, st["step"], st["streak"], st["fails"], mastered)
    return {**db.word_practice(word.lower(), tag), "advanced": advanced, "just_mastered": mastered}
