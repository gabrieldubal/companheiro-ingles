// Frases para falar: você lê, o detector compara som a som, e cada palavra trocada abre o raio-x.
import { track } from "../lib/activity.js";
import { api, form } from "../lib/api.js";
import { playBlob } from "../lib/audio.js";
import { clear, h, plural, toast } from "../lib/dom.js";
import { createRecorder, extFor } from "../lib/recorder.js";
import * as tts from "../lib/tts.js";
import { benchSplit, ladderHref, wordXray, wordsLine } from "./common.js";

const SOURCE = { leitura: "da leitura", treino: "do treino de som", "seu mundo": "do seu mundo", "sua conversa": "das suas conversas" };

export async function render(root, params, alive) {
  const q = await api("/api/phrases?n=6");
  if (!alive()) return;
  const tracker = track("frases");
  const st = { i: 0, blob: null, misses: [] };
  let recorder = null;
  const stage = h("section", { class: "stage" });
  // Ao lado do exercício: o raio-x da palavra escolhida e a fila de hoje.
  const xrayBox = h("div", { class: "side-block" });
  const queue = h("ol", { class: "queue" });
  const side = h("aside", { class: "bench-side" }, xrayBox,
    h("div", { class: "side-block" }, h("h3", "A fila de hoje"),
      q.weak.length ? h("p", { class: "soft small" }, "Puxa estes sons: ", q.weak.map((w) => `${w.symbol} ${w.label}`).join(", "), ".") : null,
      queue));
  root.append(h("header",
    h("h1", "Frases para falar"),
    h("p", "Leia em voz alta, no seu ritmo. O app compara som a som com o esperado: as palavras em verde saíram " +
           "certas; as sublinhadas tiveram um som trocado. Clique numa delas para ver o raio-x e corrigir.")),
    h("div", { class: "bench" }, h("div", { class: "bench-main" }, stage), side));
  // ✓ ou ✗ só nas frases gravadas; a pulada fica sem marca.
  const drawQueue = () => clear(queue, q.items.map((it, i) =>
    h("li", { class: i === st.i ? "cur" : i < st.i && st.missed && i in st.missed ? (st.missed[i] ? "miss" : "done") : "" },
      h("span", { class: "serif" }, it.text))));
  if (!q.items.length) {
    side.hidden = true;
    stage.append(h("div", { class: "empty" }, h("p", "Sem frases na fila agora. Faça a leitura em voz alta para o app conhecer os seus sons."),
      h("a", { class: "btn", href: "#/leitura" }, "Fazer a leitura")));
    return () => tracker.stop();
  }

  function show() {
    const it = q.items[st.i];
    const result = h("div", { class: "result" });
    const skip = h("button", { class: "btn quiet", type: "button", onclick: next }, st.i < q.items.length - 1 ? "Pular" : "Terminar");
    recorder = createRecorder({ raw: true, idle: "Aperte espaço ou clique e leia a frase.", onBlob: (b) => attempt(it, b, result, skip) });
    clear(xrayBox);
    drawQueue();
    clear(stage,
      h("p", { class: "muted small" }, `${st.i + 1} de ${q.items.length}. Foco: ${it.focus.join(" e ")}. Frase ${SOURCE[it.source] || ""}.`),
      h("div", { class: "progressbar" }, h("span", { style: { width: `${(100 * st.i) / q.items.length}%` } })),
      h("p", { class: "say" }, it.text),
      h("div", { class: "row" },
        h("button", { class: "btn secondary small", type: "button", onclick: () => tts.speak(it.text, 0.8) }, "▶ Ouvir nativo, devagar")),
      recorder.el, result, h("div", { class: "row", style: { marginTop: "12px" } }, skip));
  }

  async function attempt(it, blob, result, skip) {
    const index = st.i;
    st.blob = blob;
    tracker.bump();
    recorder.setBusy(true, "Ouvindo os sons…");
    try {
      const r = await api("/api/phrases/attempt", { body: form({ file: [blob, `frase.${extFor(blob)}`], text: it.text, source: it.source }) });
      if (!alive() || index !== st.i) return;
      const offs = r.words.filter((w) => w.offs.length);
      offs.forEach((w) => st.misses.push({ ...w, recording_id: r.recording_id, sentence: it.text }));
      st.missed = { ...(st.missed || {}), [index]: offs.length > 0 };
      const inlineX = h("div");
      const pick = (w) => {
        const x = wordXray(w, { recordingId: r.recording_id, sentence: it.text });
        if (benchSplit(xrayBox)) { clear(inlineX); clear(xrayBox, h("h3", "Raio-x da palavra"), x); }
        else { clear(xrayBox); clear(inlineX, x); }
      };
      skip.hidden = true;
      clear(result,
        r.words.length
          ? [wordsLine(r.words, pick),
             h("p", { class: "soft" }, r.score.judged
               ? (offs.length ? `${r.score.ok} de ${plural(r.score.judged, "palavra julgada saiu certa", "palavras julgadas saíram certas")}. Clique numa sublinhada.`
                              : `As ${r.score.judged} palavras que o detector julgou saíram certas.`)
               : "O detector não achou nada para julgar nesta frase.")]
          : h("p", { class: "soft" }, r.pron === "pronto"
              ? "Não deu para julgar: leia a frase inteira, no ritmo normal, e grave de novo."
              : `Detector de pronúncia: ${r.pron}.`),
        inlineX,
        h("p", { class: "small muted", style: { marginTop: "12px" } }, `O Whisper entendeu: "${r.text}"`),
        h("div", { class: "row", style: { marginTop: "10px" } },
          h("button", { class: "btn secondary small", type: "button", onclick: () => playBlob(st.blob) }, "▶ A frase inteira, você"),
          h("button", { class: "btn small", type: "button", onclick: next }, st.i < q.items.length - 1 ? "Próxima frase" : "Terminar")));
      if (offs.length) pick(offs[0]); // abre o primeiro raio-x sem precisar clicar
    } catch (e) {
      toast(e.message);
    } finally {
      recorder.setBusy(false);
    }
  }

  function next() {
    if (recorder) recorder.stop(true);
    if (st.i < q.items.length - 1) { st.i += 1; show(); return; }
    finish();
  }

  function finish() {
    st.i = q.items.length;
    clear(xrayBox);
    drawQueue();
    const seen = new Set();
    const misses = st.misses.filter((m) => {
      const key = `${m.word.toLowerCase()}:${m.offs[0].tag}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
    clear(stage,
      h("h2", misses.length ? "Palavras para corrigir desta rodada" : "Rodada terminada"),
      misses.length
        ? h("ul", { class: "list", style: { marginTop: "14px" } }, misses.map((m) => h("li", { class: "row", style: { justifyContent: "space-between" } },
            h("span", h("b", { class: "serif", style: { fontSize: "1.25rem" } }, m.word),
              m.sounds_like ? ` soou como ${m.sounds_like}` : "", h("span", { class: "small soft" }, ` (${m.offs.map((o) => o.what).join(", ")})`)),
            h("a", { class: "btn small secondary", href: ladderHref(m.offs[0].tag, m.word, m.sounds_like, m.sentence) }, "Corrigir"))))
        : h("p", { class: "soft", style: { marginTop: "8px" } }, "Nenhum som trocado nas palavras que o detector julgou."),
      h("div", { class: "row section", style: { marginTop: "22px" } },
        h("button", { class: "btn", type: "button", onclick: () => { location.hash = "#/frases"; window.dispatchEvent(new HashChangeEvent("hashchange")); } }, "Mais frases"),
        h("a", { class: "btn secondary", href: "#/hoje" }, "Voltar para hoje")));
  }

  show();
  return () => { if (recorder) recorder.stop(true); tracker.stop(); };
}
