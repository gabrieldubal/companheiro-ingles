// Ouvir você de novo: um trecho exato de uma gravação guardada, ou a gravação que acabou de fazer.
import { api } from "./api.js";
import { h, toast } from "./dom.js";
import * as tts from "./tts.js";

let current = null;
const cache = new Map();

function play(url, then) {
  if (current) current.pause();
  current = new Audio(url);
  if (then) current.addEventListener("ended", then, { once: true });
  current.play().catch(() => toast("O navegador não quis tocar o áudio."));
}

// then: o que tocar logo depois (ex.: a versão nativa, para comparar de ouvido).
export async function playClip(recordingId, start, end, then) {
  tts.stop();
  const key = `${recordingId}:${start}:${end}`;
  try {
    if (!cache.has(key)) {
      const q = start != null ? `?start=${start}&end=${end}` : "";
      const blob = await api(`/api/recordings/${recordingId}/clip${q}`);
      cache.set(key, URL.createObjectURL(blob));
    }
    play(cache.get(key), then);
  } catch (e) {
    toast(e.message);
  }
}

export function playBlob(blob) {
  tts.stop();
  play(URL.createObjectURL(blob));
}

// Os dois botões que aparecem ao lado de cada erro de pronúncia.
export function compareButtons(word, recordingId, start, end) {
  const out = [];
  if (recordingId && start != null) {
    out.push(h("button", { class: "play", type: "button", onclick: () => playClip(recordingId, start, end) }, "▶ você"));
  }
  out.push(h("button", { class: "play", type: "button", onclick: () => tts.speak(word) }, "▶ nativo"));
  return out;
}
