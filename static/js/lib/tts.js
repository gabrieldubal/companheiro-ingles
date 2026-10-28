// Voz nativa: a síntese do próprio navegador.
import { get } from "./store.js";

let voices = [];
let unlocked = false;
let defaultRate = 0.9;

function load() {
  voices = speechSynthesis.getVoices().filter((v) => (v.lang || "").toLowerCase().startsWith("en"));
}
if ("speechSynthesis" in window) {
  load();
  speechSynthesis.onvoiceschanged = load;
}

export function listVoices() {
  return voices;
}

export function setDefaultRate(r) {
  defaultRate = r;
}

function pick() {
  const uri = get("voice", "");
  return voices.find((v) => v.voiceURI === uri) || voices.find((v) => v.lang === "en-US") || voices[0] || null;
}

// O Safari só deixa falar depois de uma fala disparada por um toque: chame no próprio clique.
export function unlock() {
  if (unlocked || !("speechSynthesis" in window)) return;
  const u = new SpeechSynthesisUtterance(" ");
  u.volume = 0;
  speechSynthesis.speak(u);
  unlocked = true;
}

export function speak(text, rate) {
  if (!("speechSynthesis" in window) || !text) return;
  const u = new SpeechSynthesisUtterance(text);
  const v = pick();
  if (v) { u.voice = v; u.lang = v.lang; } else { u.lang = "en-US"; }
  u.rate = rate || get("rate", null) || defaultRate;
  if (speechSynthesis.speaking || speechSynthesis.pending) {
    speechSynthesis.cancel();
    setTimeout(() => speechSynthesis.speak(u), 60); // o Safari perde a fala se vier colada no cancel
  } else {
    speechSynthesis.speak(u);
  }
}

const ACCENT = { US: "americana", GB: "britânica", AU: "australiana", CA: "canadense", IE: "irlandesa", IN: "indiana",
                 NZ: "neozelandesa", ZA: "sul-africana", SG: "de Singapura", PH: "filipina", NG: "nigeriana", KE: "queniana" };

/** "Microsoft Zira, americana": o nome da voz sem o resto, e de onde é o sotaque. */
export function voiceLabel(v) {
  if (!v) return "voz padrão";
  const name = v.name.replace(/^(Microsoft|Google)\s+/, "").replace(/\s*[-(].*$/, "").replace(/\s+Online$/, "");
  const region = (v.lang || "").split(/[-_]/)[1]?.toUpperCase();
  return ACCENT[region] ? `${name}, ${ACCENT[region]}` : name;
}

/** Fala com uma voz escolhida e avisa quando terminou, com quanto tempo a fala durou ({ms}):
 * o treino de ouvir sorteia a voz, e o Imitar compara o seu tempo com o do nativo. */
export function say(text, { voice = null, rate = null } = {}) {
  return new Promise((resolve) => {
    if (!("speechSynthesis" in window) || !text) { resolve({ ms: 0 }); return; }
    unlock(); // no próprio clique: o Safari só fala depois de uma fala disparada por um toque
    const u = new SpeechSynthesisUtterance(text);
    const v = voice || pick();
    if (v) { u.voice = v; u.lang = v.lang; } else { u.lang = "en-US"; }
    u.rate = rate || get("rate", null) || defaultRate;
    let t0 = 0;
    u.onstart = () => (t0 = performance.now());
    u.onend = () => resolve({ ms: t0 ? Math.round(performance.now() - t0) : 0 });
    u.onerror = () => resolve({ ms: 0 });
    speechSynthesis.cancel();
    setTimeout(() => speechSynthesis.speak(u), 60);
  });
}

export function stop() {
  if ("speechSynthesis" in window) speechSynthesis.cancel();
}
