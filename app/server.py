"""Servidor do companheiro de inglês. Rode com run.bat (PC) ou celular.bat (celular)."""
import argparse
import io
import socket
import threading
import webbrowser

import uvicorn
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import onboarding, certs, config, db, drills, llm, pron, reading, stt, tutor
from .auth import TOKEN, require_token
from .media import read_upload, save_audio
from .routes import router, llm_call as _llm_call

app = FastAPI(title="Companheiro de inglês")
APP_URL = ""  # preenchidos no main()
CA_URL = ""


def _session_or_404(sid: int) -> dict:
    session = db.get_session(sid)
    if not session:
        raise HTTPException(404, "Sessão não encontrada.")
    return session


@app.get("/api/config", dependencies=[Depends(require_token)])
def api_config():
    return {
        "scenarios": tutor.scenarios_public(),
        "levels": tutor.LEVELS,
        "default_level": float(db.get_settings().get("level") or tutor.DEFAULT_LEVEL),
        "onboarding": onboarding.status()["needed"],
        "backend": llm.backend_label(),
        "whisper": config.WHISPER_MODEL,
        "whisper_ready": stt.is_ready(),
        "pron": pron.status(),
        "pron_pending": pron.pending(),
        "pattern_pt": tutor.PATTERN_PT,
        # Nome, símbolo, exemplo e como fazer cada som: o raio-x da palavra usa no navegador.
        "sounds": {tag: {"label": pron.LABEL[tag], "symbol": pron.SYMBOL[tag], "example": pron.EXAMPLE[tag],
                         "tip": drills.TIPS.get(tag)} for tag in pron.LABEL},
    }


class StartReq(BaseModel):
    scenario: str
    level: float = tutor.DEFAULT_LEVEL


@app.post("/api/sessions", dependencies=[Depends(require_token)])
def start_session(req: StartReq):
    if req.scenario not in tutor.scenarios():
        raise HTTPException(400, "Cenário desconhecido.")
    level = min(max(req.level, 1), 4)
    sid = db.create_session(req.scenario, level, tutor.recurring_now())
    session = db.get_session(sid)
    try:
        turn = _llm_call(tutor.opening, session)
    except HTTPException:
        db.delete_session(sid)  # não deixa sessão vazia no histórico
        raise
    db.add_turn(sid, "tutor", turn["reply"], turn)
    return {
        "session_id": sid,
        "turn": turn,
        "tts_rate": tutor.level_profile(level)["tts_rate"],
        "recurring": session["recurring"],
    }


class MessageReq(BaseModel):
    text: str
    recording_id: int | None = None
    unsure: list[str] = []  # palavras em que o Whisper teve dúvida


@app.post("/api/sessions/{sid}/messages", dependencies=[Depends(require_token)])
def send_message(sid: int, req: MessageReq):
    session = _session_or_404(sid)
    if session["ended_at"]:
        raise HTTPException(400, "Essa sessão já foi encerrada.")
    text = req.text.strip()[:6000]
    if not text:
        raise HTTPException(400, "Mensagem vazia.")
    turns = db.get_turns(sid)
    turn = _llm_call(tutor.respond, session, turns, text, req.unsure[:30])
    db.add_turn(sid, "student", text, {
        "corrections": turn["corrections"], "pattern_counts": turn["pattern_counts"],
        "recording_id": req.recording_id, "unsure": req.unsure[:30],
    })
    db.record_feedback(sid, turn["corrections"], turn["pattern_counts"], turn["good_uses"], turn["new_words"])
    if req.recording_id:
        db.link_recording(req.recording_id, sid, text)
    db.add_turn(sid, "tutor", turn["reply"], turn)
    return {"turn": turn}


@app.post("/api/sessions/{sid}/end", dependencies=[Depends(require_token)])
def end_session(sid: int):
    session = _session_or_404(sid)
    if session["summary"]:
        return {"summary": session["summary"]}
    summary = _llm_call(tutor.summarize, session, db.get_turns(sid), db.session_mistakes(sid))
    db.end_session(sid, summary)
    return {"summary": summary}


@app.post("/api/transcribe", dependencies=[Depends(require_token)])
async def transcribe(
    file: UploadFile = File(...),
    session_id: int | None = Form(None),
    save: bool = Form(False),
):
    audio = await read_upload(file)
    try:
        result = await run_in_threadpool(stt.transcribe, audio)
    except Exception as e:  # áudio corrompido ou formato que o PyAV não lê
        raise HTTPException(400, f"Não consegui ler o áudio: {e}")
    result["recording_id"] = None
    if save and result["text"]:
        # Guarda o áudio com a transcrição palavra por palavra: é o dataset do detector de pronúncia.
        path = save_audio(audio, file.filename, f"sessao-{session_id or 0}")
        result["recording_id"] = db.add_recording(
            session_id, path, result["text"], result["words"], result["audio_seconds"],
        )
        pron.enqueue(result["recording_id"])  # a análise de pronúncia roda em segundo plano
    return result


# --- Leitura em voz alta -------------------------------------------------------

@app.get("/api/reading", dependencies=[Depends(require_token)])
def reading_home():
    return {"sentences": reading.public(), "runs": db.reading_runs()}


@app.post("/api/reading/runs", dependencies=[Depends(require_token)])
def reading_start():
    return {"run_id": db.create_run()}


@app.post("/api/reading/runs/{rid}/record", dependencies=[Depends(require_token)])
async def reading_record(rid: int, file: UploadFile = File(...), sentence_id: str = Form(...)):
    """Neste modo o áudio é sempre guardado: é para isso que ele existe."""
    if sentence_id not in reading.BY_ID:
        raise HTTPException(400, "Frase desconhecida.")
    audio = await read_upload(file)
    try:
        # Sem a frase esperada e sem dica nenhuma, de propósito.
        result = await run_in_threadpool(stt.transcribe, audio, False)
    except Exception as e:
        raise HTTPException(400, f"Não consegui ler o áudio: {e}")
    reference = reading.BY_ID[sentence_id][1]
    compare = reading.compare(reference, result["words"])
    path = save_audio(audio, file.filename, f"leitura/rodada-{rid}", f"{sentence_id}_")
    rec_id = db.add_recording(
        None, path, result["text"], result["words"], result["audio_seconds"],
        kind="leitura", reference=reference, sentence_id=sentence_id, run_id=rid, compare=compare,
    )
    result["recording_id"] = rec_id
    result["compare"] = compare
    # Fonemas na hora: o retorno som a som aparece junto com o que o Whisper ouviu.
    await run_in_threadpool(pron.analyze_now, rec_id)
    result["checks"] = db.recording_checks(rec_id)
    result["phones"] = (db.get_recording(rec_id) or {}).get("phones")
    return result


@app.get("/api/reading/runs/{rid}", dependencies=[Depends(require_token)])
def reading_summary(rid: int):
    return reading.summarize(db.run_recordings(rid), db.run_checks(rid))


@app.post("/api/reading/runs/{rid}/finish", dependencies=[Depends(require_token)])
def reading_finish(rid: int):
    if db.finish_run(rid):
        db.add_activity("leitura", str(rid), db.run_seconds(rid))
    return reading.summarize(db.run_recordings(rid), db.run_checks(rid))


@app.get("/api/notebook", dependencies=[Depends(require_token)])
def notebook():
    return db.notebook()


@app.get("/api/history", dependencies=[Depends(require_token)])
def history():
    return {"sessions": db.history()}


@app.get("/ca.crt")
def ca_certificate():
    """A CA local, para instalar no iPhone. É pública: não tem segredo nenhum aqui."""
    if not certs.CA_CERT.exists():
        raise HTTPException(404, "Ligue o servidor no modo celular (celular.bat).")
    return Response(
        certs.ca_der(), media_type="application/x-x509-ca-cert",
        headers={"Content-Disposition": 'attachment; filename="companheiro-ca.crt"'},
    )


def _qr_svg(url: str) -> str:
    import qrcode
    import qrcode.image.svg

    buf = io.BytesIO()
    qrcode.make(url, image_factory=qrcode.image.svg.SvgPathImage, box_size=12).save(buf)
    return buf.getvalue().decode()


@app.get("/pair", response_class=HTMLResponse)
def pair(request: Request):
    """Página só para o próprio computador: mostra os QR codes que o celular escaneia."""
    if request.client.host not in ("127.0.0.1", "::1"):
        raise HTTPException(403, "Abra esta página no próprio computador.")
    ca_step = ""
    if CA_URL:
        ca_step = f"""
<section><h2>1. Uma vez só: instale o certificado</h2>
<div class="qr">{_qr_svg(CA_URL)}</div>
<ol>
<li>Aponte a câmera do iPhone e abra no <b>Safari</b>. Se aparecer "Esta conexão não é privada",
toque em <b>Mostrar Detalhes</b>, depois em <b>visitar este site</b>.</li>
<li>Permita baixar o perfil. Vá em <b>Ajustes</b>, toque em <b>Perfil Transferido</b> (no topo) e em <b>Instalar</b>.</li>
<li>Em <b>Ajustes &gt; Geral &gt; Sobre &gt; Ajustes de Confiança de Certificados</b>,
ative <b>Companheiro de ingles - CA local</b>.</li>
</ol>
<p class="small">Esse certificado só vale para endereços da sua rede de casa: não serve para
se passar por nenhum outro site. Impressão digital (SHA-256), para conferir no iPhone:<br>
<code>{certs.ca_fingerprint()}</code></p>
<p class="small">No Android, o passo 1 é opcional: dá para tocar em <b>Avançado &gt; Continuar</b> no aviso.</p>
</section><h2>2. Abra o app</h2>"""
    return f"""<!doctype html><html lang="pt-BR"><meta charset="utf-8">
<title>Parear o celular</title>
<style>
body{{font-family:system-ui;max-width:620px;margin:32px auto;padding:0 16px;color:#1f2a24;line-height:1.45}}
h1{{text-align:center}} h2{{margin-top:32px}} .qr{{width:280px;margin:12px auto}} svg{{width:100%;height:auto}}
.small{{font-size:14px;color:#555}} code{{word-break:break-all;font-size:13px}} li{{margin:6px 0}}
</style>
<body><h1>Companheiro de inglês</h1>
<p>Celular e computador no <b>mesmo Wi-Fi</b>.</p>
{ca_step}
<div class="qr">{_qr_svg(APP_URL)}</div>
<p class="small"><code>{APP_URL}</code></p>
<p>No Safari, toque em <b>Compartilhar &gt; Adicionar à Tela de Início</b> para virar um ícone.
Depois permita o microfone.</p>
</body></html>"""


app.include_router(router)


@app.middleware("http")
async def no_stale_front(request: Request, call_next):
    """O navegador guardava o JavaScript antigo e uma atualização do app só aparecia dias depois.
    "no-cache" faz ele conferir a cada carga (com ETag, a resposta é um 304 rápido quando nada mudou)."""
    response = await call_next(request)
    if not request.url.path.startswith("/api/") and not request.url.path.startswith("/fonts/"):
        response.headers["Cache-Control"] = "no-cache"
    return response


app.mount("/", StaticFiles(directory=config.STATIC, html=True), name="static")


def lan_ips() -> list[str]:
    """IP desta máquina no Wi-Fi primeiro, depois os outros."""
    ips = []
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))  # não envia nada, só descobre a interface de saída
            ips.append(s.getsockname()[0])
    except OSError:
        pass
    try:
        for ip in socket.gethostbyname_ex(socket.gethostname())[2]:
            if ip not in ips and not ip.startswith("127."):
                ips.append(ip)
    except OSError:
        pass
    return ips or ["127.0.0.1"]


def _print_qr(url: str):
    try:
        import qrcode

        qr = qrcode.QRCode(border=1)
        qr.add_data(url)
        qr.print_ascii(invert=True)
    except Exception:
        pass  # terminal sem suporte a esses caracteres: a página /pair resolve


def main():
    global APP_URL, CA_URL
    parser = argparse.ArgumentParser(description="Companheiro de inglês")
    parser.add_argument("--celular", action="store_true", help="HTTPS na rede de casa, para usar no celular")
    parser.add_argument("--http", action="store_true", help=argparse.SUPPRESS)  # antigo: o modo PC já é HTTP
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--demo", action="store_true", help="Respostas prontas, sem chamar o Claude")
    parser.add_argument("--no-browser", action="store_true", help="Não abrir o navegador sozinho")
    args = parser.parse_args()
    if args.demo:
        config.FORCED_LLM = "demo"

    threading.Thread(target=stt.load, daemon=True).start()  # o Whisper carrega enquanto você abre o app
    pron.start_worker()  # modelo de fonemas + fila das gravações que faltam analisar
    threading.Thread(target=tutor.backfill_meanings, daemon=True).start()  # erros antigos ganham o "queria dizer"
    print("\n  Companheiro de inglês")
    print(f"  Cérebro: {llm.backend_label()} | Whisper: {config.WHISPER_MODEL}")

    if not args.celular:
        # Modo PC: só este computador. Em localhost o navegador já libera o microfone, sem certificado.
        port = args.port or config.PC_PORT
        APP_URL = f"http://localhost:{port}/?t={TOKEN}"
        print(f"\n  Abra no navegador: {APP_URL}")
        print("  Para desligar: Ctrl+C\n")
        if not args.no_browser:
            threading.Timer(1.5, webbrowser.open, [APP_URL]).start()
        uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
        return

    port = args.port or config.PORT
    ips = lan_ips()
    cert, key = certs.ensure(ips)
    APP_URL = f"https://{ips[0]}:{port}/?t={TOKEN}"
    CA_URL = f"https://{ips[0]}:{port}/ca.crt"
    print(f"\n  Passo a passo com QR codes: abra https://localhost:{port}/pair neste computador")
    print(f"  Link do app (mesmo Wi-Fi): {APP_URL}\n")
    _print_qr(APP_URL)
    print("\n  Para desligar: Ctrl+C\n")
    uvicorn.run(app, host="0.0.0.0", port=port, ssl_certfile=cert, ssl_keyfile=key, log_level="warning")


if __name__ == "__main__":
    main()
