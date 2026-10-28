// Imitar (shadowing), em fluxo: o nativo fala uma frase e para; você repete no espaço que fica; a
// próxima vem sozinha. A gravação é uma só, do começo ao fim, e a análise vem no fim, frase a frase:
// os sons (raio-x) e o ritmo (o seu tempo contra o do nativo, as pausas no meio).
// Ouvir e repetir analisa só os espaços em que você fala, então funciona sem fone.
// Falar junto: você fala ao mesmo tempo que o nativo; aí precisa de fone.
import { track } from "../lib/activity.js";
import { api, form } from "../lib/api.js";
import { playClip } from "../lib/audio.js";
import { clear, h, toast } from "../lib/dom.js";
import { createRecorder, extFor } from "../lib/recorder.js";
import { get, set } from "../lib/store.js";
import * as tts from "../lib/tts.js";
import { app } from "../main.js";
import { wordsLine, wordXray } from "./common.js";

const SYMBOL = (tag) => app.config?.sounds?.[tag]?.symbol || tag;
const num = (x) => (Number.isInteger(x) ? x.toFixed(1) : String(x)).replace(".", ",");
const GAPS = [[1.2, "curto"], [1.6, "médio"], [2.1, "longo"]]; // o espaço para repetir, em vezes a fala do nativo
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

export async function render(root, [pid], alive) {
  const d = await api("/api/imitar");
  if (!alive()) return;
  if (!pid) return renderHub(root, d, alive);
  const p = d.passages.find((x) => String(x.id) === pid);
  if (!p) { location.hash = "#/imitar"; return; }
  return renderPassage(root, p, d, alive);
}

function progressText(p, rates) {
  const n = p.sentences.length;
  const passedAt = (r) => p.sentences.filter((_, i) => (p.progress || {})[i] >= r).length;
  const best = rates.slice().reverse().find((r) => passedAt(r) >= n);
  const some = Object.keys(p.progress || {}).filter((k) => k !== "-1").length;
  if (best) return `todas as frases passaram em ${num(best)}`;
  return some ? `${some} de ${n} frases passaram` : "ainda não praticado";
}

function renderHub(root, d, alive) {
  const list = h("ul", { class: "grid-list", style: { "--col": "460px" } });
  const gen = h("button", { class: "btn secondary", type: "button" }, "Gerar textos do meu mundo");
  gen.onclick = async () => {
    gen.disabled = true;
    gen.textContent = "Escrevendo com o Claude…";
    try {
      await api("/api/imitar/gerar", { body: {} });
      if (!alive()) return;
      window.dispatchEvent(new HashChangeEvent("hashchange"));
    } catch (e) {
      toast(e.message);
      gen.disabled = false;
      gen.textContent = "Gerar textos do meu mundo";
    }
  };
  clear(list, d.passages.map((p) => h("li", { class: "row", style: { justifyContent: "space-between", alignItems: "flex-start" } },
    h("div", { style: { flex: 1, minWidth: "260px" } },
      h("h3", { style: { fontFamily: "var(--sans)", fontSize: "var(--step-0)" } }, p.title),
      h("p", { class: "serif", style: { fontSize: "1.1rem", marginTop: "4px" } }, p.sentences.join(" ")),
      h("p", { class: "small muted", style: { marginTop: "4px" } },
        (p.focus.length ? `Sons: ${p.focus.slice(0, 4).map(SYMBOL).join(", ")}. ` : "") + progressText(p, d.rates) + ".")),
    h("a", { class: "btn small", href: `#/imitar/${p.id}` }, "Imitar"))));
  root.append(h("header",
    h("p", { class: "date-line" }, h("a", { href: "#/pronuncia" }, "Pronúncia"), " / imitar"),
    h("h1", "Imitar"),
    h("p", "Textos curtos com as suas frases corrigidas e os seus sons fracos. O nativo fala uma frase e para, você repete " +
           "no espaço que fica, e a próxima vem sozinha, do começo ao fim. No final, o app analisa o conjunto: os sons de " +
           "cada frase e o ritmo, contra o do nativo. A velocidade sobe de 0,8 para 1,0.")),
    h("div", { class: "row", style: { marginBottom: "18px" } }, gen,
      h("span", { class: "soft small" }, "Três textos novos sobre a sua vida e o seu trabalho. Uns 15 segundos.")),
    list);
}

function renderPassage(root, p, d, alive) {
  const tracker = track("imitar", String(p.id));
  const progress = { ...(p.progress || {}) };
  let mode = get("shadowMode", "eco");
  let gap = get("shadowGap", 1.6);
  let showText = get("shadowText", true);
  // Começa na menor velocidade em que ainda falta passar alguma frase.
  let rate = d.rates.find((r) => p.sentences.some((_, i) => !(progress[i] >= r))) || d.rates[d.rates.length - 1];
  let only = null; // índices para a próxima rodada ("só as que não passaram")
  let recorder = null;
  let run = null; // a rodada em andamento
  const controls = h("div", { class: "shadow-controls" });
  const stage = h("section", { class: "stage" });
  // Ao lado: como vai ser a rodada (antes de começar) e até onde cada frase já passou.
  const passedList = h("ol", { class: "queue" });
  const drawPassed = () => clear(passedList, p.sentences.map((t, i) => h("li", { class: progress[i] ? "done" : "" },
    h("span", { class: "serif" }, t), h("span", { class: "sub" }, progress[i] ? `passou em ${num(progress[i])}` : "ainda não passou"))));
  root.append(h("header",
    h("p", { class: "date-line" }, h("a", { href: "#/imitar" }, "Imitar"), ` / ${p.title}`),
    h("h1", p.title),
    h("p", "O nativo fala uma frase e para; você repete no espaço que fica; a próxima vem sozinha. A análise vem no fim, " +
           "frase a frase. Ouvir e repetir funciona sem fone: o app só analisa os espaços em que você fala.")),
    h("div", { class: "bench", style: { marginTop: "18px" } }, h("div", { class: "bench-main" }, stage),
      h("aside", { class: "bench-side lead" }, h("div", { class: "side-block" }, h("h3", "A rodada"), controls),
        h("div", { class: "side-block wide-only" }, h("h3", "Neste texto"), passedList))));
  drawPassed();

  function seg(cur, opts, on, label) {
    return h("div", { class: "control" }, h("span", { class: "small muted" }, label),
      h("div", { class: "mode-switch", role: "group", "aria-label": label }, opts.map(([v, text]) =>
        h("button", { type: "button", "aria-pressed": String(cur === v), disabled: !!run, onclick: () => on(v) }, text))));
  }

  function drawControls() {
    const textBox = h("input", { type: "checkbox", disabled: !!run });
    textBox.checked = showText;
    textBox.onchange = () => { showText = textBox.checked; set("shadowText", showText); idle(); };
    clear(controls,
      seg(mode, [["eco", "Ouvir e repetir"], ["junto", "Falar junto (fone)"]], (v) => { mode = v; set("shadowMode", v); drawControls(); idle(); }, "Modo"),
      seg(rate, d.rates.map((r) => [r, num(r)]), (v) => { rate = v; drawControls(); idle(); }, "Velocidade"),
      mode === "eco" ? seg(gap, GAPS, (v) => { gap = v; set("shadowGap", v); drawControls(); }, "Espaço para repetir") : null,
      h("label", { class: "check", style: { margin: 0 } }, textBox, "Mostrar o texto"));
  }

  const queue = () => p.sentences.map((t, i) => ({ index: i, text: t })).filter((s) => !only || only.includes(s.index));

  function idle() {
    if (recorder) recorder.stop(true);
    const list = queue();
    recorder = createRecorder({
      raw: true,
      idle: mode === "eco" ? "Aperte espaço ou clique para começar. Espaço de novo termina antes do fim."
                           : "Ponha o fone. Aperte espaço ou clique: o nativo começa e você fala junto.",
      onStart: () => flow(list),
      onBlob: (b) => finishRun(b),
    });
    clear(stage,
      h("ol", { class: "flow-list" }, list.map((s) => h("li", showText ? s.text : "…"))),
      recorder.el,
      only ? h("p", { class: "small muted" }, `Só as ${list.length === 1 ? "1 frase que não passou" : `${list.length} frases que não passaram`}. `,
        h("button", { class: "btn quiet small", type: "button", onclick: () => { only = null; idle(); } }, "Fazer o texto todo")) : null);
  }

  async function flow(list) {
    const me = (run = { segments: [], stopped: false, t0: performance.now() });
    drawControls();
    const now = () => (performance.now() - me.t0) / 1000;
    // O gravador descarta uma gravação curtinha (clique duplo no microfone) sem mandar nada: aí a
    // rodada acaba aqui, em vez de deixar os controles travados e o nativo falando sozinho.
    const dropped = () => {
      if (me.stopped || run !== me || recorder?.recording) return false;
      me.stopped = true;
      run = null;
      tts.stop();
      drawControls();
      idle();
      return true;
    };
    const status = h("p", { class: "flow-status" });
    const bar = h("div", { class: "flow-bar" }, h("span"));
    const sentence = h("p", { class: "say" });
    const counter = h("p", { class: "muted small" });
    clear(stage, counter, sentence, status, bar, recorder.el);
    for (const [k, s] of list.entries()) {
      if (me.stopped || !alive()) return;
      counter.textContent = `Frase ${k + 1} de ${list.length}`;
      sentence.textContent = showText ? s.text : "…";
      sentence.classList.remove("yours");
      status.textContent = mode === "eco" ? "Ouça" : "Fale junto";
      bar.firstChild.style.transition = "none";
      bar.firstChild.style.width = "0";
      const ns = now();
      await tts.say(s.text, { rate });
      const ne = now();
      if (me.stopped || dropped()) return;
      const native = Math.max(ne - ns, 0.8);
      const wait = mode === "eco" ? native * gap + 0.6 : 0.7;
      if (mode === "eco") {
        status.textContent = "Sua vez";
        sentence.classList.add("yours");
        bar.firstChild.style.transition = `width ${wait}s linear`;
        requestAnimationFrame(() => (bar.firstChild.style.width = "100%"));
      }
      await sleep(wait * 1000);
      if (me.stopped || dropped()) return;
      me.segments.push({ index: s.index, native_start: ns, native_end: ne, gap_end: now() });
    }
    if (!me.stopped && recorder?.recording) recorder.stop(false); // fim do texto: manda o conjunto
  }

  async function finishRun(blob) {
    const me = run;
    if (!me) return;
    me.stopped = true;
    tts.stop();
    run = null;
    drawControls();
    if (!me.segments.length) { toast("Nenhuma frase completa: deixe o nativo terminar e repita no espaço."); idle(); return; }
    tracker.bump();
    clear(stage, h("p", { class: "soft" }, `Analisando o conjunto: ${me.segments.length} ${me.segments.length === 1 ? "frase" : "frases"}…`));
    try {
      const r = await api("/api/imitar/conjunto", { body: form({
        file: [blob, `imitar.${extFor(blob)}`], passage_id: String(p.id), segments: JSON.stringify(me.segments),
        rate: String(rate), mode,
      }) });
      if (!alive()) return;
      r.items.forEach((it) => { if (it.ok) progress[it.index] = Math.max(progress[it.index] || 0, rate); });
      drawPassed();
      showResult(r);
    } catch (e) {
      toast(e.message);
      idle();
    }
  }

  function showResult(r) {
    const failed = r.items.filter((it) => !it.ok).map((it) => it.index);
    const faster = d.rates.find((x) => x > rate);
    const parts = [];
    if (r.sounds.length) parts.push(`Os sons que mais escaparam: ${r.sounds.slice(0, 3).map((s) => `${s.symbol} (${s.words.slice(0, 3).join(", ")})`).join("; ")}.`);
    if (r.ratio) parts.push(`Em média você levou ${num(r.ratio)}x o tempo do nativo.`);
    clear(stage,
      h("h2", `${r.passed} de ${r.total} ${r.total === 1 ? "frase passou" : "frases passaram"} em ${num(rate)}`),
      parts.length ? h("p", { class: "soft", style: { marginTop: "6px" } }, parts.join(" ")) : null,
      h("p", { class: "small muted", style: { marginTop: "4px" } }, `Passa com os sons certos e até ${num(d.pass_ratio)}x o tempo do nativo.`),
      h("ol", { class: "flow-results" }, r.items.map((it) => {
        const xray = h("div");
        const rh = it.rhythm;
        return h("li", { class: it.ok ? "ok" : "no" },
          h("div", { class: "row", style: { justifyContent: "space-between", alignItems: "baseline" } },
            h("span", { class: "mark" }, it.ok ? "✓" : "✗"),
            h("div", { style: { flex: 1 } },
              it.words?.length ? wordsLine(it.words, (w) => clear(xray, wordXray(w, { recordingId: it.recording_id, sentence: it.text })))
                : h("p", { class: "serif" }, it.text),
              h("p", { class: "small soft" }, it.empty ? "Não deu para ouvir você nesse espaço."
                : (rh ? `Você ${num(rh.you)} s` + (rh.native ? `, nativo ${num(rh.native)} s (${num(rh.ratio)}x)` : "") +
                       (rh.pauses?.length ? `. Pausas: ${rh.pauses.map((x) => `depois de "${x.after}"`).join(", ")}` : "") + "." : "") +
                  (it.transcript ? ` O Whisper entendeu: "${it.transcript}"` : ""))),
            h("span", { class: "row", style: { gap: "6px" } },
              it.recording_id ? h("button", { class: "play", type: "button", onclick: () => playClip(it.recording_id, it.start, it.end) }, "▶ Você") : null,
              h("button", { class: "play", type: "button", onclick: () => tts.say(it.text, { rate }) }, "▶ Nativo"))),
          xray);
      })),
      h("div", { class: "row section", style: { marginTop: "20px" } },
        failed.length ? h("button", { class: "btn", type: "button", onclick: () => { only = failed; idle(); } },
          failed.length === 1 ? "Repetir a que não passou" : `Repetir as ${failed.length} que não passaram`) : null,
        !failed.length && faster ? h("button", { class: "btn", type: "button", onclick: () => { rate = faster; only = null; drawControls(); idle(); } },
          `Subir para ${num(faster)}`) : null,
        h("button", { class: "btn secondary", type: "button", onclick: () => { only = null; idle(); } }, "O texto todo de novo"),
        h("a", { class: "btn secondary", href: "#/usar" }, "Agora com as suas palavras"),
        h("a", { class: "btn quiet", href: "#/imitar" }, "Outro texto")));
    // Abre sozinho o raio-x da primeira palavra que saiu trocada.
    const firstOff = r.items.flatMap((it) => (it.words || []).map((w) => [it, w])).find(([, w]) => w.offs?.length);
    if (firstOff) {
      const li = stage.querySelectorAll(".flow-results > li")[r.items.indexOf(firstOff[0])];
      li?.lastChild && clear(li.lastChild, wordXray(firstOff[1], { recordingId: firstOff[0].recording_id, sentence: firstOff[0].text }));
    }
  }

  drawControls();
  idle();
  return () => {
    if (run) run.stopped = true;
    if (recorder) recorder.stop(true);
    tts.stop();
    tracker.stop();
  };
}
