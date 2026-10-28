"""Rotas da versão 2: plano do dia, erros, progresso, treinos, "fale certo" e ajustes."""
import asyncio
import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from pydantic import BaseModel

from datetime import datetime, timedelta

from . import (ask, config, db, deck, drills, freetalk, ladder, lessons, listen, llm, onboarding, phrases, plan, pron,
               reading, shadow, stt, tutor)
from .auth import require_token
from .media import clip_wav, read_upload, save_audio

router = APIRouter(prefix="/api", dependencies=[Depends(require_token)])


def llm_call(fn, *args):
    try:
        return fn(*args)
    except llm.LLMError as e:
        raise HTTPException(502, str(e))


async def _transcribe(audio: bytes, conversation: bool = False) -> dict:
    try:
        return await run_in_threadpool(stt.transcribe, audio, conversation)
    except Exception as e:  # áudio corrompido ou formato que o PyAV não lê
        raise HTTPException(400, f"Não consegui ler o áudio: {e}")


# --- Hoje, erros e progresso --------------------------------------------------------

@router.get("/today")
def today(silent: bool = False):
    return plan.today(silent)


@router.get("/errors")
def errors():
    return {"sounds": plan.pron_profile(), "grammar": plan.grammar_profile(),
            "words": db.notebook()["words"], "pron": pron.status(), "pron_pending": pron.pending()}


@router.get("/progress")
def progress():
    return plan.progress()


# --- Treino de som ------------------------------------------------------------------

@router.get("/drills/{tag}")
def drill(tag: str):
    try:
        out = drills.session(tag)
    except KeyError:
        raise HTTPException(404, "Som desconhecido.")
    out["profile"] = next((s for s in plan.pron_profile() if s["tag"] == tag), None)
    out["pron"] = pron.status()
    out["listen"] = tag in listen.PAIRS
    return out


@router.post("/drills/{tag}/generate")
def drill_generate(tag: str):
    if tag not in drills.ITEMS:
        raise HTTPException(404, "Som desconhecido.")
    profile = config.PROFILE.read_text(encoding="utf-8") if config.PROFILE.exists() else ""
    items = llm_call(drills.generate, tag, profile)
    if not items:
        raise HTTPException(502, "O Claude não devolveu frases boas para esse som. Tente de novo.")
    return {"items": items}


@router.post("/drills/{tag}/attempt")
async def drill_attempt(tag: str, file: UploadFile = File(...), text: str = Form(...), targets: str = Form("[]")):
    if tag not in drills.ITEMS:
        raise HTTPException(404, "Som desconhecido.")
    audio = await read_upload(file)
    result = await _transcribe(audio)
    path = save_audio(audio, file.filename, f"treino/{tag}")
    rid = db.add_recording(None, path, result["text"], result["words"], result["audio_seconds"],
                           kind="treino", reference=text, sentence_id=f"drill:{tag}")
    await run_in_threadpool(pron.analyze_now, rid)
    checks = db.recording_checks(rid)
    return {
        "recording_id": rid, "text": result["text"], "compare": reading.compare(text, result["words"]),
        "target": drills.judge(tag, json.loads(targets or "[]"), checks), "checks": checks,
        "pron": pron.status(),
    }


# --- Frases para falar, raio-x e escada de correção ------------------------------------

def _analyzed(rid: int) -> dict:
    """Checagens e raio-x de uma gravação recém-analisada."""
    rec = db.get_recording(rid) or {}
    words = pron.realign(rec) if rec else []
    for w in words:  # cada troca vem com o que fazer diferente
        for o in w.get("offs") or []:
            o["fix"] = drills.fix_for({**o, "ok": False})
    return {"checks": db.recording_checks(rid), "words": words}


@router.get("/phrases")
def phrases_queue(n: int = 6):
    return phrases.queue(min(max(n, 1), 12))


@router.post("/phrases/attempt")
async def phrases_attempt(file: UploadFile = File(...), text: str = Form(...), source: str = Form("")):
    audio = await read_upload(file)
    result = await _transcribe(audio)
    path = save_audio(audio, file.filename, "frases")
    rid = db.add_recording(None, path, result["text"], result["words"], result["audio_seconds"],
                           kind="frase", reference=text, sentence_id=f"frase:{source[:20]}")
    await run_in_threadpool(pron.analyze_now, rid)
    out = _analyzed(rid)
    judged = [w for w in out["words"] if w["judged"]]
    return {"recording_id": rid, "text": result["text"], **out, "pron": pron.status(),
            "score": {"ok": sum(1 for w in judged if w["ok"]), "judged": len(judged)}}


@router.get("/recordings/{rid}/words")
def recording_words(rid: int):
    """Raio-x de uma gravação antiga (refeito dos sons guardados, sem rodar o modelo)."""
    rec = db.get_recording(rid)
    if not rec:
        raise HTTPException(404, "Gravação não encontrada.")
    return {"words": pron.realign(rec), "reference": rec["reference"] or rec["sent_text"] or rec["transcript"]}


@router.get("/problem-words")
def problem_words():
    since = (datetime.now() - timedelta(days=90)).isoformat(timespec="seconds")
    rows = db.problem_words(since)
    aligned = {}  # raio-x por gravação, refeito uma vez só (é rápido: não roda o modelo)
    for r in rows:
        r["label"] = pron.LABEL.get(r["tag"], r["tag"])
        r["symbol"] = pron.SYMBOL.get(r["tag"], "")
        r["heard_as"] = None
        rid = r.get("recording_id")
        if rid:
            if rid not in aligned:
                rec = db.get_recording(rid)
                aligned[rid] = pron.realign(rec) if rec else []
            w = next((x for x in aligned[rid] if x["word"].lower() == r["word"] and not x["ok"]), None)
            r["heard_as"] = w["sounds_like"] if w else None
    return {"words": rows}


class LadderStepReq(BaseModel):
    tag: str
    word: str
    step: int


@router.post("/ladder/step")
def ladder_step(req: LadderStepReq):
    """Descer (ou voltar) um degrau por escolha sua, depois de alguns erros seguidos."""
    st = db.word_practice(req.word.lower(), req.tag)
    db.save_word_practice(req.word.lower(), req.tag, max(0, req.step), 0, 0, False)
    return {**db.word_practice(req.word.lower(), req.tag), "previous": st["step"]}


@router.get("/ladder")
def ladder_get(tag: str, word: str, heard_as: str | None = None, sentence: str | None = None):
    if tag not in drills.ITEMS:
        raise HTTPException(404, "Som desconhecido.")
    st = db.word_practice(word.lower(), tag)
    last = db.problem_words("2000-01-01", limit=500)
    miss = next((p for p in last if p["word"] == word.lower() and p["tag"] == tag), None)
    if st["mastered_at"] and miss and miss["last_seen"] > st["mastered_at"]:
        db.restart_word_practice(word.lower(), tag)  # errou de novo depois de vencer: recomeça
        st = db.word_practice(word.lower(), tag)
    # O degrau fica guardado pela posição, então a lista de degraus da palavra tem que ser sempre
    # a mesma, venha você de onde vier: o "soou como" é decidido uma vez e guardado.
    heard = st["heard_as"]
    if heard is None:
        heard = heard_as or _heard_as(word.lower(), tag, miss) or ""
        db.set_word_heard(word.lower(), tag, heard)
    return ladder.session(tag, word, heard or None, sentence)


def _heard_as(word: str, tag: str, miss: dict | None) -> str | None:
    rec = db.get_recording(miss["recording_id"]) if miss and miss.get("recording_id") else None
    hit = next((x for x in pron.realign(rec) if x["word"].lower() == word and not x["ok"]), None) if rec else None
    return hit["sounds_like"] if hit else None


@router.post("/ladder/attempt")
async def ladder_attempt(file: UploadFile = File(...), tag: str = Form(...), word: str = Form(...),
                         text: str = Form(...), targets: str = Form("[]"), steps: int = Form(...)):
    if tag not in drills.ITEMS:
        raise HTTPException(404, "Som desconhecido.")
    audio = await read_upload(file)
    result = await _transcribe(audio)
    path = save_audio(audio, file.filename, f"escada/{tag}")
    rid = db.add_recording(None, path, result["text"], result["words"], result["audio_seconds"],
                           kind="escada", reference=text, sentence_id=f"escada:{tag}:{word.lower()}")
    await run_in_threadpool(pron.analyze_now, rid)
    out = _analyzed(rid)
    wanted = json.loads(targets or "[]")
    judged = drills.judge(tag, wanted, out["checks"])
    ok = bool(judged) and all(c["ok"] for c in judged)
    db.set_compare(rid, {"ok": ok, "judged": bool(judged), "targets": wanted})  # para a lista de tentativas
    state = ladder.record(tag, word, steps, ok) if judged else {**db.word_practice(word.lower(), tag),
                                                                 "advanced": False, "just_mastered": False}
    attempt = next(iter(db.ladder_attempts(tag, word.lower(), limit=1)), None)
    if attempt and attempt["recording_id"] == rid:
        attempt["fix"] = drills.fix_for(attempt)
    else:
        attempt = None
    return {"recording_id": rid, "text": result["text"], **out, "target": judged, "ok": ok,
            "judged": bool(judged), "state": state, "pron": pron.status(), "attempt": attempt}


# --- Cartões -------------------------------------------------------------------------------

@router.get("/deck/session")
def deck_session(mais: int = 0):
    """`mais`: puxa cartões novos além do limite do dia (o botão "Mais novos agora")."""
    return deck.session(mais)


@router.get("/deck")
def deck_list(q: str = "", kind: str = ""):
    deck.sync()
    return {"cards": [deck.public(c) for c in db.list_cards(q.strip()[:80], kind)], "summary": deck.summary()}


class AnswerReq(BaseModel):
    rating: int


@router.post("/deck/cards/{cid}/answer")
def deck_answer(cid: int, req: AnswerReq):
    try:
        return deck.answer(cid, req.rating)
    except KeyError:
        raise HTTPException(404, "Cartão não encontrado.")


class CheckReq(BaseModel):
    text: str


@router.post("/deck/cards/{cid}/check")
def deck_check(cid: int, req: CheckReq):
    """Responder escrevendo: confere a resposta digitada e sugere a nota (quem dá a nota é você)."""
    try:
        return deck.check(cid, req.text)
    except KeyError:
        raise HTTPException(404, "Cartão não encontrado.")
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/deck/undo")
def deck_undo():
    try:
        return deck.undo()
    except KeyError:
        raise HTTPException(404, "Nenhuma nota para desfazer hoje.")


class CardReq(BaseModel):
    front: str
    back: str
    note: str = ""


@router.post("/deck/cards")
def deck_create(req: CardReq):
    try:
        cid = deck.create("livre", req.front, req.back, req.note)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return deck.public(db.get_card(cid))


class CardEditReq(BaseModel):
    front: str | None = None
    back: str | None = None
    note: str | None = None
    suspended: bool | None = None


@router.put("/deck/cards/{cid}")
def deck_edit(cid: int, req: CardEditReq):
    c = db.get_card(cid)
    if not c or c["deleted"]:
        raise HTTPException(404, "Cartão não encontrado.")
    fields = {k: v.strip()[:600] for k, v in (("front", req.front), ("back", req.back), ("note", req.note)) if v is not None}
    if fields.get("front") == "" or fields.get("back") == "":
        raise HTTPException(400, "O cartão precisa de frente e verso.")
    back, note = fields.get("back", c["back"]), fields.get("note", c["note"] or "")
    if c["kind"] == "palavra":  # o áudio e a lacuna saem da palavra e do exemplo
        fields["speak"] = f"{back}. {note}" if note else back
        fields["hint"] = deck.cloze(back, note)
    elif "back" in fields:
        fields["speak"] = back
    if req.suspended is not None:
        fields["suspended"] = int(req.suspended)
    db.update_card(cid, **fields)
    return deck.public(db.get_card(cid))


@router.delete("/deck/cards/{cid}")
def deck_delete(cid: int):
    db.delete_card(cid)
    return {"ok": True}


# --- Ouvir a diferença ---------------------------------------------------------------------

@router.get("/listen")
def listen_get():
    return listen.stats()


class TrialReq(BaseModel):
    tag: str
    word: str
    other: str
    chosen: str
    voice: str = ""


@router.post("/listen/trial")
def listen_trial(req: TrialReq):
    try:
        return {"ok": listen.record(req.tag, req.word, req.other, req.chosen, req.voice)}
    except KeyError:
        raise HTTPException(404, "Par desconhecido.")


# --- Perguntar -----------------------------------------------------------------------------

@router.get("/ask")
def ask_get():
    thread = db.ask_thread()
    return {"thread": thread, "messages": db.ask_messages(thread)}


class AskReq(BaseModel):
    text: str


@router.post("/ask")
async def ask_post(req: AskReq):
    text = req.text.strip()[:4000]
    if not text:
        raise HTTPException(400, "Escreva a pergunta.")
    thread = db.ask_thread()
    # A sua mensagem só é guardada junto com a resposta: se o Claude falhar, ela fica na caixa de texto.
    out = await run_in_threadpool(llm_call, ask.reply, thread, text)
    db.add_ask_message(thread, "user", text)
    mid = db.add_ask_message(thread, "assistant", out["text"], out["actions"])
    return {"message": db.get_ask_message(mid)}


@router.post("/ask/new")
def ask_new():
    """Conversa nova: a anterior fica guardada, mas sai do contexto."""
    thread = db.ask_thread()
    if db.ask_messages(thread, limit=1):
        thread += 1
        db.set_setting("ask_thread", str(thread))  # guardado: a próxima pergunta já cai na conversa nova
    return {"thread": thread, "messages": []}


@router.post("/ask/messages/{mid}/actions/{i}/undo")
def ask_undo(mid: int, i: int):
    m = db.get_ask_message(mid)
    if not m or i >= len(m["actions"]) or m["actions"][i].get("undone") or "undo" not in m["actions"][i]:
        raise HTTPException(404, "Nada para desfazer.")
    ask.undo(m["actions"][i])
    m["actions"][i]["undone"] = True
    db.set_ask_actions(mid, m["actions"])
    return {"message": db.get_ask_message(mid)}


# --- Imitar (shadowing) -----------------------------------------------------------------

@router.get("/imitar")
def imitar_list():
    return {"passages": shadow.passages(), "rates": shadow.RATES, "pass_ratio": shadow.PASS_RATIO}


@router.post("/imitar/gerar")
def imitar_generate():
    return {"passages": llm_call(shadow.generate)}


@router.post("/imitar/conjunto")
async def imitar_set(file: UploadFile = File(...), passage_id: int = Form(...), segments: str = Form(...),
                     rate: float = Form(0.9), mode: str = Form("eco")):
    """O texto inteiro de uma vez: o nativo fala, você repete no espaço, e a análise vem no fim."""
    p = db.get_passage(passage_id)
    if not p:
        raise HTTPException(404, "Texto não encontrado.")
    try:
        segs = json.loads(segments)
    except ValueError:
        raise HTTPException(400, "Trechos inválidos.")
    if not segs:
        raise HTTPException(400, "Nenhuma frase completa nessa gravação.")
    audio = await read_upload(file)
    try:
        return await run_in_threadpool(shadow.analyze_set, audio, file.filename, p, segs, rate,
                                       "junto" if mode == "junto" else "eco")
    except Exception as e:  # áudio corrompido ou formato que o PyAV não lê
        raise HTTPException(400, f"Não consegui analisar a gravação: {e}")


@router.post("/imitar/attempt")
async def imitar_attempt(file: UploadFile = File(...), passage_id: int = Form(...), index: int = Form(...),
                         text: str = Form(...), rate: float = Form(0.9), mode: str = Form("eco"),
                         native_ms: int = Form(0)):
    if not db.get_passage(passage_id):
        raise HTTPException(404, "Texto não encontrado.")
    audio = await read_upload(file)
    result = await _transcribe(audio)
    path = save_audio(audio, file.filename, "imitar")
    rid = db.add_recording(None, path, result["text"], result["words"], result["audio_seconds"],
                           kind="imitar", reference=text, sentence_id=f"imitar:{passage_id}:{index}")
    await run_in_threadpool(pron.analyze_now, rid)
    out = _analyzed(rid)
    rh = shadow.rhythm(result["words"], native_ms)
    ok = shadow.passed(out["words"], rh)
    db.set_compare(rid, {"ok": ok, "rate": rate, "mode": mode, "rhythm": rh})
    return {"recording_id": rid, "text": result["text"], **out, "rhythm": rh, "ok": ok, "pron": pron.status()}


# --- Usar livre --------------------------------------------------------------------------

@router.get("/usar")
def usar_queue(kind: str | None = None, ref: str | None = None):
    if kind and kind not in ("padrao", "som"):
        raise HTTPException(404, "Alvo desconhecido.")
    return {"prompts": llm_call(freetalk.queue, kind, ref)}


@router.post("/usar/attempt")
async def usar_attempt(file: UploadFile = File(...), prompt_id: int = Form(...), unsure: str = Form("[]")):
    p = db.get_prompt(prompt_id)
    if not p:
        raise HTTPException(404, "Pergunta não encontrada.")
    audio = await read_upload(file)
    result = await _transcribe(audio, conversation=True)
    if not result["text"]:
        raise HTTPException(400, "Não deu para ouvir nada nessa gravação. Fale um pouco mais perto do microfone.")
    path = save_audio(audio, file.filename, "usar")
    rid = db.add_recording(None, path, result["text"], result["words"], result["audio_seconds"],
                           kind="usar", sentence_id=f"usar:{prompt_id}")
    doubts = [w["w"] for w in result["words"] if w.get("unsure")][:20]
    # O detector e o Claude ao mesmo tempo: a resposta chega quando os dois terminam.
    _, ev = await asyncio.gather(run_in_threadpool(pron.analyze_now, rid),
                                 run_in_threadpool(llm_call, freetalk.evaluate, p, result["text"], doubts))
    sound = None
    if p["kind"] == "som":
        cs = [c for c in db.recording_checks(rid) if c["tag"] == p["ref"]]
        sound = {"tag": p["ref"], "symbol": pron.SYMBOL.get(p["ref"], ""), "n": len(cs),
                 "off": sum(1 for c in cs if not c["ok"])}
        ev["used_target"] = bool(cs)
        ev["target_ok"] = bool(cs) and not sound["off"]
    freetalk.apply(p, ev, result["text"], rid)
    return {"recording_id": rid, "text": result["text"], "evaluation": ev, "sound": sound, **_analyzed(rid),
            "pron": pron.status()}


# --- Entender ----------------------------------------------------------------------------

@router.get("/entender")
def entender_trilha():
    return {"items": lessons.trilha()}


@router.get("/entender/aula")
def entender_aula(key: str, refazer: bool = False):
    try:
        return llm_call(lessons.get, key, refazer)
    except KeyError:
        raise HTTPException(404, "Aula desconhecida.")


class LessonScoreReq(BaseModel):
    key: str
    score: int
    total: int


@router.post("/entender/nota")
def entender_nota(req: LessonScoreReq):
    db.score_lesson(req.key, max(0, req.score), max(0, req.total))
    return {"ok": True}


class LessonKeyReq(BaseModel):
    key: str


@router.post("/entender/cartoes")
def entender_cartoes(req: LessonKeyReq):
    try:
        return {"created": lessons.add_cards(req.key)}
    except KeyError:
        raise HTTPException(404, "Faça a aula antes de levar os cartões.")


# --- Fale certo ------------------------------------------------------------------------

@router.get("/practice")
def practice():
    items = db.practice_items(limit=6)
    for it in items:
        it["label"] = tutor.PATTERN_PT.get(it["pattern"], it["pattern"])
        it["changed"] = reading.changed_words(it["original"], it["better"])  # marcadas na resposta
    return {"items": items}


def _tolerance(target: str) -> int:
    return reading.tolerance(target)


@router.post("/practice/attempt")
async def practice_attempt(file: UploadFile = File(...), mistake_id: int = Form(...), pattern: str = Form(...),
                           target: str = Form(...)):
    audio = await read_upload(file)
    result = await _transcribe(audio)
    cmp = reading.compare(target, result["words"])
    m = db.get_mistake(mistake_id)
    verdict = reading.judge_correction(m["original"] if m else "", target, result["text"], _tolerance(target))
    ok = verdict["ok"]
    path = save_audio(audio, file.filename, "fale-certo")
    rid = db.add_recording(None, path, result["text"], result["words"], result["audio_seconds"],
                           kind="fale-certo", reference=target, sentence_id=f"mistake:{mistake_id}")
    db.add_practice("fale-certo", pattern, mistake_id, target, result["text"], ok, rid)
    db.practice_result(pattern, ok)
    pron.enqueue(rid)
    return {"ok": ok, "text": result["text"], "compare": cmp, "recording_id": rid, **verdict}


class TypedReq(BaseModel):
    mistake_id: int
    pattern: str
    target: str
    text: str


@router.post("/practice/typed")
def practice_typed(req: TypedReq):
    """Fale certo por escrito (onde não dá para falar): a mesma conferência, sem o Whisper."""
    text = req.text.strip()[:500]
    if not text:
        raise HTTPException(400, "Escreva a frase antes de conferir.")
    cmp = reading.compare(req.target, [{"w": w} for w in text.split()])
    m = db.get_mistake(req.mistake_id)
    verdict = reading.judge_correction(m["original"] if m else "", req.target, text, _tolerance(req.target))
    ok = verdict["ok"]
    db.add_practice("fale-certo-escrito", req.pattern, req.mistake_id, req.target, text, ok, None)
    db.practice_result(req.pattern, ok)
    return {"ok": ok, "text": text, "compare": cmp, **verdict}


# --- Boas-vindas (a primeira vez de cada pessoa) -----------------------------------------

@router.get("/onboarding")
def onboarding_status():
    return onboarding.status()


class CodeReq(BaseModel):
    code: str


@router.post("/onboarding/codigo")
def onboarding_code(req: CodeReq):
    try:
        return {"backend": llm_call(onboarding.connect, req.code), **onboarding.status()}
    except ValueError as e:
        raise HTTPException(400, str(e))


class ProfileReq(BaseModel):
    name: str = ""
    nickname: str = ""
    level: float | None = None
    goal: str = ""
    work: str = ""
    interests: str = ""
    life: str = ""
    struggles: str = ""
    names: str = ""


@router.post("/onboarding/perfil")
def onboarding_profile(req: ProfileReq):
    if len((req.goal + req.work + req.interests).strip()) < 10:
        raise HTTPException(400, "Conte pelo menos para que você precisa do inglês e o que você faz.")
    onboarding.save_profile(req.model_dump())
    return onboarding.status()


@router.post("/onboarding/cenarios")
def onboarding_scenarios():
    return {"created": llm_call(tutor.generate_scenarios), **onboarding.status()}


# --- Atividade, ajustes e áudio ---------------------------------------------------------

class ActivityReq(BaseModel):
    kind: str
    ref: str = ""
    seconds: int


@router.post("/activity")
def activity(req: ActivityReq):
    if req.kind not in ("conversa", "treino", "fale-certo", "leitura", "frases", "escada", "cartoes", "ouvir",
                        "perguntar", "imitar", "usar", "entender") or req.seconds < 5:
        return {"ok": False}
    db.add_activity(req.kind, req.ref[:60], req.seconds)
    return {"ok": True}


@router.get("/settings")
def get_settings():
    return {
        **db.get_settings(),
        "profile": config.PROFILE.read_text(encoding="utf-8") if config.PROFILE.exists() else "",
        "vocab": config.VOCAB.read_text(encoding="utf-8") if config.VOCAB.exists() else "",
        "backend": llm.backend_label(), "whisper": config.WHISPER_MODEL, "pron": pron.status(),
        "data_dir": str(config.DATA), "brain": llm.available(), "version": config.VERSION,
    }


class SettingsReq(BaseModel):
    weekly_target: int | None = None
    session_minutes: int | None = None
    goal: str | None = None
    profile: str | None = None
    vocab: str | None = None
    cards_per_day: int | None = None
    focus_tag: str | None = None


@router.put("/settings")
def put_settings(req: SettingsReq):
    if req.weekly_target is not None:
        db.set_setting("weekly_target", str(min(max(req.weekly_target, 1), 7)))
    if req.session_minutes is not None:
        db.set_setting("session_minutes", str(min(max(req.session_minutes, 5), 60)))
    if req.goal is not None:
        db.set_setting("goal", req.goal.strip()[:300])
    if req.cards_per_day is not None:
        db.set_setting("cards_per_day", str(min(max(req.cards_per_day, 0), 50)))
    if req.focus_tag is not None and (req.focus_tag in pron.LABEL or not req.focus_tag):
        db.set_setting("focus_tag", req.focus_tag)
    if req.profile is not None:
        config.PROFILE.write_text(req.profile.strip() + "\n", encoding="utf-8")
    if req.vocab is not None:
        config.VOCAB.write_text(req.vocab.strip() + "\n", encoding="utf-8")
    return get_settings()


@router.get("/recordings/{rid}/clip")
def recording_clip(rid: int, start: float | None = None, end: float | None = None):
    rec = db.get_recording(rid)
    if not rec or not rec["path"]:
        raise HTTPException(404, "Gravação não encontrada.")
    try:
        return Response(clip_wav(rec["path"], start, end), media_type="audio/wav")
    except FileNotFoundError:
        raise HTTPException(404, "O arquivo dessa gravação não está mais em data/audio.")


@router.get("/sessions/{sid}/pron")
def session_pron(sid: int):
    recs = db.session_recordings(sid)
    checks = [c for r in recs for c in db.recording_checks(r["id"])]
    sounds = sorted(pron.summarize_checks(checks).values(), key=lambda s: -s["off"])
    off = [c | {"recording_id": r["id"]} for r in recs for c in db.recording_checks(r["id"]) if not c["ok"]]
    ready = pron.status() == "pronto"
    # Só está "analisando" o que ainda vai ser analisado: erro ou detector desligado não contam.
    pending = sum(1 for r in recs if r["pron_status"] in (None, "pending")) if ready else 0
    return {"recordings": len(recs), "pending": pending, "sounds": sounds, "off": off[:12], "pron": pron.status()}
