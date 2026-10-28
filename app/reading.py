"""Leitura em voz alta: frases fixas que miram os sons difíceis para quem fala português.

O conjunto é fixo de propósito. Gravar as mesmas frases daqui a um mês mostra o que mudou,
e o texto conhecido é o que o detector de fonemas precisa para comparar o esperado com o falado.
"""
import difflib
import re

# (id, frase, foco em português, etiquetas do som-alvo)
SENTENCES = [
    ("th-1", "I think three months is enough time.", "th sem voz: think, three, months", ["th-voiceless"]),
    ("th-2", "This is the weather my mother likes.", "th com voz: this, the, weather, mother", ["th-voiced"]),
    ("fin-1", "I worked in the office with a big dog.", "vogal extra no fim: office, big, dog", ["final-vowel", "ed-t"]),
    ("fin-2", "My job is to stop bad data at the start.", "finais sem vogal: job, stop, bad, start", ["final-vowel", "s-cluster"]),
    ("s-1", "I study at a school in Spain.", "s inicial sem 'e' na frente: study, school, Spain", ["s-cluster"]),
    ("r-1", "The red river runs near the road.", "r inicial em inglês, não 'rr': red, river, road", ["r-initial"]),
    ("r-2", "I'm very sorry about the errors.", "r entre vogais: very, sorry, errors", ["r-intervocalic"]),
    ("h-1", "He had a red hat in his hand.", "h aspirado e r: had, hat, hand, red", ["h", "r-initial"]),
    ("i-1", "I live here, but I leave tomorrow.", "i curto e i longo: live, leave", ["i-short-long"]),
    ("i-2", "The ship is full of sheep.", "i curto e i longo: ship, sheep", ["i-short-long"]),
    ("i-3", "Please sit in this seat.", "i curto e i longo: sit, seat", ["i-short-long"]),
    ("ae-1", "The bad man sat on the bed.", "æ aberto e é: bad, man, bed", ["ae-e"]),
    ("ed-1", "I played, worked, and wanted to rest.", "-ed: played (d), worked (t), wanted (id)", ["ed-d", "ed-t", "ed-id"]),
    ("ed-2", "We visited Machu Picchu and walked for five days.", "-ed: visited (id), walked (t)", ["ed-id", "ed-t"]),
    ("s-2", "The model needs more data and uses less memory.", "s final audível: needs, uses", ["final-s"]),
    ("s-3", "She works with maps, and he watches the forest.", "s final e terceira pessoa: works, watches", ["final-s"]),
    ("n-1", "The team has a plan for the long run.", "m, n e ng no fim, sem nasalizar: team, plan, long", ["final-nasal"]),
    ("t-1", "It is a pretty city with a different culture.", "t e d sem virar 'tch' e 'dj': pretty, city, different", ["t-d-palatal"]),
    ("l-1", "People feel well in a small school.", "l no fim, sem virar 'u': people, feel, well", ["dark-l"]),
    ("st-1", "I want to develop a comfortable vegetable garden.", "sílaba forte: deVElop, COMfortable, VEGetable", ["stress"]),
    ("pair-1", "ship, sheep. live, leave. sit, seat.", "pares mínimos: i curto e i longo", ["i-short-long", "pairs"]),
    ("pair-2", "bad, bed. man, men. had, head.", "pares mínimos: æ e é", ["ae-e", "pairs"]),
    ("pair-3", "think, sink. three, tree. thank, tank.", "pares mínimos: th", ["th-voiceless", "pairs"]),
    ("pair-4", "rat, hat. red, head. rope, hope.", "pares mínimos: r e h", ["r-initial", "h", "pairs"]),
]
BY_ID = {s[0]: s for s in SENTENCES}

TAG_PT = {
    "th-voiceless": "th sem voz (think)", "th-voiced": "th com voz (this)",
    "final-vowel": "vogal extra no fim", "s-cluster": "'e' antes de s (school)",
    "r-initial": "r inicial", "r-intervocalic": "r entre vogais", "h": "h aspirado",
    "i-short-long": "i curto e longo", "ae-e": "æ e é", "ed-d": "-ed como d", "ed-t": "-ed como t",
    "ed-id": "-ed como id", "final-s": "s final", "final-nasal": "m/n/ng no fim",
    "t-d-palatal": "t e d antes de i", "dark-l": "l no fim", "stress": "sílaba forte", "pairs": "pares mínimos",
}


def public() -> list:
    return [{"id": i, "text": t, "focus_pt": f, "tags": tags} for i, t, f, tags in SENTENCES]


# O Whisper escreve "3" quando você fala "three": não é diferença de som.
_NUMBERS = dict(enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen "
    "fifteen sixteen seventeen eighteen nineteen twenty".split()
))


def _norm(token: str) -> str:
    t = re.sub(r"[^a-z0-9']", "", token.lower())
    return _NUMBERS.get(int(t), t) if t.isdigit() else t


def _bare(word: str) -> str:
    return re.sub(r"[.,!?;:\"]", "", word).strip()


def compare(reference: str, words: list) -> dict:
    """Alinha a frase esperada com o que o Whisper ouviu, palavra por palavra.

    O Whisper NÃO recebe a frase esperada. Então, quando ele ouve "sink" onde estava
    escrito "think", é uma pista de que o som saiu diferente. É uma pista fraca: às vezes
    ele "corrige" sozinho pelo contexto. O veredito de verdade virá do modelo de fonemas.
    """
    ref_tokens = reference.split()
    ref_norm = [_norm(t) for t in ref_tokens]
    hyp = [w for w in words if _norm(w["w"])]
    hyp_norm = [_norm(w["w"]) for w in hyp]
    out = [{"w": t, "status": "ok", "heard": ""} for t in ref_tokens]
    matcher = difflib.SequenceMatcher(a=ref_norm, b=hyp_norm, autojunk=False)
    for op, a1, a2, b1, b2 in matcher.get_opcodes():
        if op == "equal":
            for k in range(a2 - a1):
                if hyp[b1 + k].get("unsure"):
                    out[a1 + k]["status"] = "unsure"
        elif op == "replace" and a2 - a1 == b2 - b1:
            # Mesmo número de palavras: pareia uma a uma ("sheep" -> ouviu "ship").
            for k in range(a2 - a1):
                out[a1 + k]["status"] = "diff"
                out[a1 + k]["heard"] = _bare(hyp[b1 + k]["w"])
        elif op in ("replace", "delete"):
            heard = " ".join(_bare(w["w"]) for w in hyp[b1:b2])
            for k in range(a1, a2):
                out[k]["status"] = "diff"
            out[a1]["heard"] = heard or "(nada)"
    diffs = sum(1 for t in out if t["status"] == "diff")
    return {"tokens": out, "diffs": diffs, "unsure": sum(1 for t in out if t["status"] == "unsure")}


def summarize(recordings: list, checks_by_rec: dict | None = None) -> dict:
    """Resumo de uma rodada.

    by_sound: som a som, pelo detector de fonemas (o veredito).
    by_tag: frases em que o Whisper ouviu outra palavra (a pista antiga, fica como referência).
    """
    from . import pron

    checks_by_rec = checks_by_rec or {}
    latest = {}
    for r in recordings:  # vale a última gravação de cada frase
        latest[r["sentence_id"]] = r
    by_tag, by_sound, items = {}, {}, []
    for sid, text, focus, tags in SENTENCES:
        r = latest.get(sid)
        if not r:
            continue
        cmp = r["compare"]
        checks = checks_by_rec.get(r.get("id"), [])
        flagged = cmp["diffs"] > 0 or cmp["unsure"] > 0
        items.append({"id": sid, "text": text, "focus_pt": focus, "compare": cmp, "transcript": r["transcript"],
                      "recording_id": r.get("id"), "off": [c for c in checks if not c["ok"]]})
        for tag in tags:
            t = by_tag.setdefault(tag, {"tag": tag, "label": TAG_PT.get(tag, tag), "sentences": 0, "flagged": 0})
            t["sentences"] += 1
            t["flagged"] += int(flagged)
        for c in checks:
            s = by_sound.setdefault(c["tag"], {"tag": c["tag"], "label": pron.LABEL.get(c["tag"], c["tag"]),
                                               "symbol": pron.SYMBOL.get(c["tag"], ""), "n": 0, "off": 0,
                                               "native": pron.NATIVE_RATE.get(c["tag"], (0, 1))})
            s["n"] += 1
            s["off"] += int(not c["ok"])
    for s in by_sound.values():
        k, n = s["native"]
        s["native"] = k / n
    ranked = sorted(by_tag.values(), key=lambda t: (-t["flagged"] / max(t["sentences"], 1), -t["flagged"]))
    sounds = sorted(by_sound.values(), key=lambda s: (-(s["off"] / s["n"] - s["native"]), -s["n"]))
    return {"recorded": len(items), "total": len(SENTENCES), "by_tag": ranked, "by_sound": sounds,
            "items": items}


# --- Fale certo: a correção tem que aparecer, e o erro não pode ficar --------------------------
# Antes, uma palavra diferente era tolerada (ruído do Whisper), e se essa palavra fosse justamente
# a do erro ("give the journey" no lugar de "give the direction"), o app dizia "Isso".
_CONTRACTIONS = {
    "won't": "will not", "can't": "can not", "cannot": "can not", "shan't": "shall not",
    "i'm": "i am", "it's": "it is", "that's": "that is", "he's": "he is", "she's": "she is",
    "what's": "what is", "there's": "there is", "here's": "here is", "let's": "let us",
}
_NO_APOSTROPHE = {w.replace("'", ""): w for w in (
    "don't", "doesn't", "didn't", "isn't", "aren't", "wasn't", "weren't", "haven't", "hasn't", "hadn't",
    "couldn't", "shouldn't", "wouldn't", "won't", "can't", "i'm")}


def _expanded(text: str) -> list[str]:
    out = []
    for raw in text.split():
        t = _norm(raw)
        if not t:
            continue
        t = _CONTRACTIONS.get(t, t)
        if t in _NO_APOSTROPHE:  # "doesnt" digitado sem apóstrofo
            t = _NO_APOSTROPHE[t]
        if t.endswith("n't"):
            t = f"{t[:-3]} not"
        else:
            for suf, full in (("'re", " are"), ("'ve", " have"), ("'ll", " will"), ("'d", " would")):
                if t.endswith(suf):
                    t = t[: -len(suf)] + full
                    break
        out += t.split()
    return out


def tolerance(target: str) -> int:
    """Quantas palavras fora do ponto do erro podem sair diferentes (frase longa, mais folga)."""
    n = len(target.split())
    return 0 if n <= 7 else (1 if n <= 15 else 2)


def changed_words(original: str, better: str) -> list[int]:
    """Posições, na versão certa, das palavras que a correção trouxe (para marcar na resposta)."""
    a = [_norm(t) for t in original.split()]
    b = [_norm(t) for t in better.split()]
    sm = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
    return [k for op, _, _, b1, b2 in sm.get_opcodes() if op in ("replace", "insert") for k in range(b1, b2) if b[k]]


def judge_correction(original: str, better: str, said: str, tolerance: int) -> dict:
    """Acertou se: as palavras novas da correção estão lá, as erradas sumiram, e o resto bate."""
    o, b, s = _expanded(original), _expanded(better), _expanded(said)
    sm = difflib.SequenceMatcher(a=o, b=b, autojunk=False)
    key, wrong = [], []
    for op, a1, a2, b1, b2 in sm.get_opcodes():
        if op in ("replace", "insert"):
            key += b[b1:b2]
        if op in ("replace", "delete"):
            wrong += [w for w in o[a1:a2] if w not in b]
    heard = set(s)
    missing = list(dict.fromkeys(w for w in key if w not in heard))
    kept = list(dict.fromkeys(w for w in wrong if w in heard))
    matched = sum(m.size for m in difflib.SequenceMatcher(a=b, b=s, autojunk=False).get_matching_blocks())
    other = len(b) - matched
    ok = bool(s) and not missing and not kept and other <= tolerance
    return {"ok": ok, "missing": missing, "kept": kept, "fixed": [w for w in dict.fromkeys(key) if w in heard]}
