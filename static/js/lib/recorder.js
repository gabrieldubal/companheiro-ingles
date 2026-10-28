// Botão de gravar: clique ou barra de espaço começa, de novo termina. Um por tela.
import { h, toast } from "./dom.js";
import * as tts from "./tts.js";

const MIC_ICON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/></svg>';

function pickMime() {
  if (!window.MediaRecorder) return null;
  const options = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg;codecs=opus"];
  return options.find((m) => MediaRecorder.isTypeSupported(m)) || "";
}

export function extFor(blob) {
  return blob.type.includes("mp4") ? "m4a" : blob.type.includes("ogg") ? "ogg" : "webm";
}

let active = null; // só um gravador escuta a barra de espaço

document.addEventListener("keydown", (e) => {
  if (e.code !== "Space" || e.repeat || !active || !active.button.isConnected) return;
  if (["TEXTAREA", "INPUT", "SELECT", "BUTTON", "A"].includes(document.activeElement.tagName)) return;
  e.preventDefault();
  active.toggle();
});

/**
 * raw: sem filtro de ruído (leitura e treino: o filtro deforma os sons que o detector mede).
 * onBlob(blob): o que fazer com a gravação.
 */
export function createRecorder({ raw = false, idle = "Aperte espaço ou clique para falar.", onBlob, onStart }) {
  const button = h("button", { class: "mic", type: "button", "aria-label": "Gravar" });
  button.innerHTML = MIC_ICON; // ícone fixo, sem dado do usuário
  const hint = h("p", { class: "hint" });
  const el = h("div", { class: "recorder" }, button, hint);
  let rec = null, stream = null, chunks = [], started = 0, timer = null, discard = false, busy = false;
  let starting = false; // entre o clique e o navegador liberar o microfone

  function setHint(text) {
    hint.replaceChildren();
    const parts = text.split("espaço");
    if (parts.length === 2) hint.append(parts[0], h("kbd", "espaço"), parts[1]);
    else hint.append(text);
  }
  setHint(idle);

  async function start() {
    const mime = pickMime();
    if (!navigator.mediaDevices?.getUserMedia || mime === null) {
      toast("Microfone indisponível neste navegador. Abra pelo endereço localhost que aparece na janela preta do app.", 7000);
      return;
    }
    tts.stop();
    starting = true;
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: raw ? { echoCancellation: false, noiseSuppression: false, autoGainControl: false }
                   : { echoCancellation: true, noiseSuppression: true },
      });
    } catch {
      toast("Sem permissão para usar o microfone. Libere no cadeado da barra de endereço.");
      return;
    } finally {
      starting = false;
    }
    if (!button.isConnected || busy) { // saiu da tela enquanto o microfone abria
      stream.getTracks().forEach((t) => t.stop());
      return;
    }
    rec = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
    chunks = [];
    discard = false;
    rec.ondataavailable = (e) => e.data.size && chunks.push(e.data);
    rec.onstop = () => {
      stream.getTracks().forEach((t) => t.stop());
      const type = rec.mimeType || "audio/webm";
      rec = null;
      button.classList.remove("rec");
      clearInterval(timer);
      setHint(idle);
      if (discard) return;
      const blob = new Blob(chunks, { type });
      if (Date.now() - started < 700 || blob.size < 1500) {
        toast("Curtinho demais. Clique, fale e clique de novo.");
        return;
      }
      onBlob(blob);
    };
    rec.start();
    started = Date.now();
    button.classList.add("rec");
    button.setAttribute("aria-label", "Parar e enviar");
    const tick = () => setHint(`Gravando… ${Math.round((Date.now() - started) / 1000)} s. Espaço ou clique para terminar.`);
    tick();
    timer = setInterval(tick, 500);
    onStart && onStart();
  }

  const api = {
    el, button,
    toggle() {
      tts.unlock();
      if (busy || starting) return;
      if (rec) rec.stop();
      else start();
    },
    stop(drop = true) {
      if (rec) { discard = drop; rec.stop(); }
    },
    setBusy(on, label) {
      busy = on;
      button.disabled = on;
      setHint(on ? label || "Analisando…" : idle);
    },
    setIdle(text) { idle = text; if (!rec && !busy) setHint(idle); },
    get recording() { return !!rec; },
  };
  button.addEventListener("click", () => api.toggle());
  active = api;
  return api;
}
