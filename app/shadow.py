"""Imitar (shadowing): textos curtos do seu mundo; o nativo fala e você repete, ou fala junto.

O retorno tem duas partes: os sons, pelo detector de sempre, e o ritmo, que o app não media:
quanto tempo você levou contra o nativo na mesma velocidade, e onde você parou no meio da frase.
A velocidade sobe de 0,8 para 1,0: é falando rápido que o "three" vira "tree".
"""
import re

from . import db, drills, llm, phrases, plan, pron, tutor

PAUSE = 0.35  # silêncio entre duas palavras que conta como pausa (o nativo liga as palavras)
PASS_RATIO = 1.35  # passa se levar até 35% a mais que o nativo
RATES = [0.8, 0.9, 1.0]

_STR = {"type": "string"}
SCHEMA = {
    "type": "object",
    "properties": {"passages": {"type": "array", "items": {
        "type": "object",
        "properties": {"title": _STR, "sentences": {"type": "array", "items": _STR}},
        "required": ["title", "sentences"],
        "additionalProperties": False,
    }}},
    "required": ["passages"],
    "additionalProperties": False,
}


def weak_sounds() -> list[dict]:
    return [s for s in plan.pron_profile() if s["status"] in ("treinar", "atenção") and s["rate"] >= 0.05]


def _focus(sentences: list[str], tags: list[str]) -> list[str]:
    text = " ".join(sentences)
    return [t for t in tags if t in drills.ITEMS and drills.sound_words(t, text)]


def _title(focus: list[str]) -> str:
    return "Sons: " + ", ".join(pron.SYMBOL.get(t, t) for t in focus[:3]) if focus else "Frases suas"


def _sentence(t: str) -> str:
    """As frases corrigidas do caderno às vezes são pedaços: ganham maiúscula e ponto para ler como frase."""
    t = t.strip()
    t = t[:1].upper() + t[1:]
    return t if t[-1:] in ".?!" else t + "."


def seed() -> list[dict]:
    """Sem Claude: textos montados com as frases da fila (os seus sons fracos e as suas correções)."""
    items = [_sentence(it["text"]) for it in phrases.queue(9)["items"]]
    tags = [s["tag"] for s in weak_sounds()]
    for k in range(0, len(items) - 2, 3):
        group = items[k:k + 3]
        focus = _focus(group, tags)
        db.add_passage(_title(focus), group, focus, "banco")
    return db.passages()


def passages() -> list[dict]:
    rows = db.passages()
    if not rows:
        rows = seed()
    for r in rows:
        r["progress"] = db.passage_progress(r["id"])
    return rows


def generate() -> list[dict]:
    """Três textos novos do seu mundo, com as suas frases corrigidas e os seus sons fracos."""
    weak = weak_sounds()[:4]
    fixed = db.recent_mistakes(10)
    words = [w["word"] for w in db.problem_words("2000-01-01", limit=12)]
    system = ("You write short texts for spoken-English shadowing practice for a Brazilian learner around B1. "
              "Natural spoken English, the way a person would say it in a call, not written prose.")
    prompt = (
        f"Learner profile (Portuguese):\n{tutor._profile_text()}\n\n"
        "Sounds they mispronounce (include many words with them): "
        + ", ".join(f"{s['label']} (as in {s['example']})" for s in weak) + "\n"
        f"Words where a sound came out wrong: {', '.join(words) or '(none)'}\n"
        "Their own corrected sentences (reuse some of them as they are, inside the texts):\n"
        + "\n".join(f"- {m['better']}" for m in fixed) + "\n\n"
        "Write 3 texts. Each text: a title in Brazilian Portuguese (2 to 5 words) and 3 or 4 sentences that "
        "connect as a tiny story or explanation about the learner's own life or work. Each sentence 6 to 14 "
        "words, easy to say in one breath, no lists, no semicolons."
    )
    data = llm.complete_json(system, prompt, SCHEMA)
    tags = [s["tag"] for s in weak]
    made = []
    for p in (data.get("passages") or [])[:3]:
        sentences = [re.sub(r"\s+", " ", s).strip() for s in p.get("sentences", []) if s and s.strip()]
        sentences = [s for s in sentences if 3 <= len(s.split()) <= 20][:4]
        if len(sentences) >= 2:
            focus = _focus(sentences, tags)
            made.append(db.add_passage(str(p.get("title") or _title(focus)).strip()[:60], sentences, focus, "claude"))
    return [db.get_passage(i) for i in made]


def _bare(w: str) -> str:
    return re.sub(r"[^\w'-]", "", w)


def rhythm(words: list[dict], native_ms: int | None) -> dict | None:
    """O seu tempo contra o do nativo, e as pausas no meio da frase."""
    ws = [w for w in words or [] if w.get("w") and w.get("end") is not None]
    if not ws:
        return None
    you = max(ws[-1]["end"] - ws[0]["start"], 0.1)
    pauses = [{"after": _bare(ws[i]["w"]), "seconds": round(ws[i + 1]["start"] - ws[i]["end"], 2)}
              for i in range(len(ws) - 1) if ws[i + 1]["start"] - ws[i]["end"] >= PAUSE]
    native = (native_ms or 0) / 1000
    ratio = round(you / native, 2) if native >= 0.5 else None
    return {"you": round(you, 1), "native": round(native, 1) if native >= 0.5 else None, "ratio": ratio,
            "pauses": pauses[:6]}


def analyze_set(audio: bytes, filename: str, passage: dict, segments: list[dict], rate: float, mode: str) -> dict:
    """O conjunto gravado de uma vez: cada frase é analisada no trecho em que você falou.

    Ouvir e repetir: o trecho é o espaço depois da fala do nativo (a voz dele, vinda da caixa de som,
    fica de fora). Falar junto: o trecho é o tempo da fala do nativo (aí precisa de fone).
    Cada trecho vira uma gravação própria (mesmo arquivo, tempos do conjunto), para os botões ▶ e o
    raio-x funcionarem como no resto do app.
    """
    from . import stt  # o Whisper só carrega quando precisa
    from .media import save_audio

    samples = stt._decode(audio)
    total = len(samples) / pron.SR
    path = save_audio(audio, filename, "imitar")
    sentences = passage["sentences"]
    items = []
    for seg in segments:
        idx = int(seg.get("index", -1))
        if not 0 <= idx < len(sentences):
            continue
        text = sentences[idx]
        ns, ne = float(seg.get("native_start", 0)), float(seg.get("native_end", 0))
        a, b = (ne - 0.1, float(seg.get("gap_end", ne))) if mode == "eco" else (ns - 0.1, ne + 0.6)
        a, b = max(a, 0.0), min(b + 0.15, total)
        piece = samples[int(a * pron.SR): int(b * pron.SR)]
        if b - a < 0.5:
            items.append({"index": idx, "text": text, "empty": True, "ok": False})
            continue
        tr = stt.transcribe_samples(piece, conversation=False)
        shifted = [{**w, "start": round(w["start"] + a, 2), "end": round(w["end"] + a, 2)} for w in tr["words"]]
        rid = db.add_recording(None, path, tr["text"], shifted, round(b - a, 1), kind="imitar", reference=text,
                               sentence_id=f"imitar:{passage['id']}:{idx}")
        words = []
        if tr["words"] and pron.status() == "pronto":
            res = pron.analyze(piece, tr["words"], text)
            checks = [{**c, "start": round(c["start"] + a, 2) if c.get("start") is not None else None,
                       "end": round(c["end"] + a, 2) if c.get("end") is not None else None} for c in res["checks"]]
            db.save_pron(rid, res["phones"], checks, "imitar")
            words = pron.realign(db.get_recording(rid))
            for w in words:
                for o in w.get("offs") or []:
                    o["fix"] = drills.fix_for({**o, "ok": False})
        rh = rhythm(tr["words"], int((ne - ns) * 1000))
        ok = passed(words, rh)
        db.set_compare(rid, {"ok": ok, "rate": rate, "mode": mode, "rhythm": rh})
        items.append({"index": idx, "text": text, "recording_id": rid, "start": round(a, 2), "end": round(b, 2),
                      "transcript": tr["text"], "words": words, "rhythm": rh, "ok": ok, "empty": not tr["words"]})
    sounds = {}
    for it in items:
        for w in it.get("words") or []:
            for o in w.get("offs") or []:
                s = sounds.setdefault(o["tag"], {"tag": o["tag"], "symbol": pron.SYMBOL.get(o["tag"], o["tag"]),
                                                 "label": pron.LABEL.get(o["tag"], o["tag"]), "n": 0, "words": []})
                s["n"] += 1
                if w["word"] not in s["words"]:
                    s["words"].append(w["word"])
    ratios = [it["rhythm"]["ratio"] for it in items if it.get("rhythm") and it["rhythm"].get("ratio")]
    return {"items": items, "passed": sum(1 for it in items if it["ok"]), "total": len(items),
            "sounds": sorted(sounds.values(), key=lambda s: -s["n"]),
            "ratio": round(sum(ratios) / len(ratios), 2) if ratios else None}


def passed(words: list[dict], rh: dict | None) -> bool:
    judged = [w for w in words if w.get("judged")]
    sounds_ok = all(w["ok"] for w in judged)
    return bool(judged) and sounds_ok and (rh is None or rh["ratio"] is None or rh["ratio"] <= PASS_RATIO)
