// Usar livre ("com as suas palavras"): uma pergunta feita para puxar a forma que você corrigiu ou o
// som que você treinou. Você responde falando, e o app confere se a correção apareceu na fala livre.
import { track } from "../lib/activity.js";
import { api, form } from "../lib/api.js";
import { playBlob } from "../lib/audio.js";
import { clear, h, toast } from "../lib/dom.js";
import { createRecorder, extFor } from "../lib/recorder.js";
import * as tts from "../lib/tts.js";
import { benchSplit, wordsLine, wordXray } from "./common.js";

export async function render(root, [kind, ref], alive) {
  root.append(h("header",
    h("p", { class: "date-line" }, h("a", { href: "#/hoje" }, "Hoje"), " / com as suas palavras"),
    h("h1", "Com as suas palavras"),
    h("p", "Uma pergunta feita para puxar o que você corrigiu, sem dizer o que é. Pense uns segundos e responda falando, " +
           "de 20 a 40 segundos. O app confere se a forma certa apareceu e como saíram os sons: é o teste de que a " +
           "correção pegou.")));
  const stage = h("section", { class: "stage" }, h("p", { class: "soft" }, "Preparando as perguntas…"));
  // Ao lado: o raio-x da palavra que você clicar e as perguntas desta rodada.
  const xrayBox = h("div", { class: "side-block" });
  const queue = h("ol", { class: "queue" });
  const side = h("aside", { class: "bench-side", hidden: true }, xrayBox, h("div", { class: "side-block" }, h("h3", "As perguntas"), queue));
  root.append(h("div", { class: "bench section", style: { marginTop: "12px" } }, h("div", { class: "bench-main" }, stage), side));
  const marks = {};
  const drawQueue = () => clear(queue, prompts.map((x, k) => h("li", { class: marks[k] || (k === i ? "cur" : "") },
    x.kind === "som" ? `o som ${x.symbol} (${x.label})` : x.label)));
  const q = kind ? `?kind=${encodeURIComponent(kind)}&ref=${encodeURIComponent(ref || "")}` : "";
  let prompts;
  try {
    prompts = (await api(`/api/usar${q}`)).prompts;
  } catch (e) {
    clear(stage, h("p", { class: "empty" }, e.message));
    return;
  }
  if (!alive()) return;
  const tracker = track("usar", kind ? `${kind}:${ref}` : "");
  let i = 0;
  let recorder = null;

  function show() {
    if (recorder) recorder.stop(true);
    const p = prompts[i];
    if (!p) { done(); return; }
    side.hidden = false;
    clear(xrayBox);
    drawQueue();
    const pt = h("p", { class: "soft", hidden: true }, p.question_pt);
    const result = h("div", { class: "result" });
    recorder = createRecorder({ raw: true, idle: "Pense, aperte espaço (ou clique) e responda. Fale até uns 40 segundos.",
                                onBlob: (b) => attempt(p, b, result) });
    clear(stage,
      h("p", { class: "muted small" }, `${i + 1} de ${prompts.length}. Alvo: ${p.kind === "som" ? `o som ${p.symbol} (${p.label})` : p.label}.`),
      h("p", { class: "question" }, p.question_en),
      h("div", { class: "row" },
        h("button", { class: "btn secondary small", type: "button", onclick: () => tts.speak(p.question_en, 0.85) }, "▶ Ouvir a pergunta"),
        h("button", { class: "btn quiet small", type: "button", onclick: () => (pt.hidden = !pt.hidden) }, "Em português")),
      pt, recorder.el, result,
      h("div", { class: "row", style: { marginTop: "14px" } },
        h("button", { class: "btn quiet", type: "button", onclick: next }, i < prompts.length - 1 ? "Pular" : "Terminar")));
  }

  async function attempt(p, blob, result) {
    tracker.bump();
    const t0 = Date.now();
    recorder.setBusy(true, "Ouvindo e avaliando a resposta…");
    const tick = setInterval(() => recorder.setBusy(true, `Ouvindo e avaliando a resposta… ${Math.round((Date.now() - t0) / 1000)} s`), 1000);
    try {
      const r = await api("/api/usar/attempt", { body: form({ file: [blob, `usar.${extFor(blob)}`], prompt_id: String(p.id) }) });
      if (!alive() || prompts[i] !== p) return;
      const ev = r.evaluation;
      marks[i] = ev.used_target && ev.target_ok ? "done" : "miss";
      drawQueue();
      const inlineX = h("div");
      const pick = (w) => {
        const x = wordXray(w, { recordingId: r.recording_id });
        if (benchSplit(xrayBox)) { clear(inlineX); clear(xrayBox, h("h3", "Raio-x da palavra"), x); }
        else { clear(xrayBox); clear(inlineX, x); }
      };
      const head = ev.used_target && ev.target_ok
        ? ["A forma certa apareceu na fala livre.", "var(--mata)"]
        : ev.used_target ? ["Você usou, mas o erro voltou.", "var(--pitaya)"] : ["Dessa vez a forma não apareceu.", "var(--ink-2)"];
      clear(result,
        h("h3", { style: { color: head[1] } }, head[0]),
        r.sound ? h("p", r.sound.n
          ? `O ${r.sound.symbol} apareceu ${r.sound.n} ${r.sound.n === 1 ? "vez" : "vezes"} e saiu certo em ${r.sound.n - r.sound.off}.`
          : `Nenhuma palavra com ${r.sound.symbol} apareceu na resposta.`) : null,
        ev.verdict_pt ? h("p", { style: { marginTop: "6px" } }, ev.verdict_pt) : null,
        h("p", { class: "soft small", style: { marginTop: "12px" } }, "Você disse (clique numa palavra marcada para ver o som):"),
        r.words?.length ? wordsLine(r.words, pick) : h("p", { class: "serif" }, r.text),
        inlineX,
        ev.corrections?.length ? h("div", { class: "fixes" }, ev.corrections.map((c) => h("div", { class: "fix" },
          h("p", { class: "line" }, h("del", c.original), "  ", h("ins", c.better)),
          c.explanation_pt ? h("p", { class: "why" }, c.explanation_pt) : null))) : null,
        ev.better ? h("div", { style: { marginTop: "14px" } }, h("p", { class: "soft small" }, "Uma versão natural da sua resposta:"),
          h("p", { class: "better" }, ev.better)) : null,
        h("div", { class: "row", style: { marginTop: "12px" } },
          h("button", { class: "btn secondary small", type: "button", onclick: () => playBlob(blob) }, "▶ Você"),
          ev.better ? h("button", { class: "btn secondary small", type: "button", onclick: () => tts.speak(ev.better, 0.9) }, "▶ A versão natural") : null,
          h("button", { class: "btn small secondary", type: "button", onclick: show }, "Responder de novo"),
          h("button", { class: "btn small", type: "button", onclick: next }, i < prompts.length - 1 ? "Próxima pergunta" : "Terminar")));
    } catch (e) {
      toast(e.message);
    } finally {
      clearInterval(tick);
      recorder.setBusy(false);
    }
  }

  function next() {
    i += 1;
    show();
  }

  function done() {
    if (recorder) recorder.stop(true);
    clear(xrayBox);
    if (prompts.length) drawQueue(); else side.hidden = true;
    const more = h("button", { class: "btn", type: "button" }, "Mais perguntas");
    more.onclick = async () => {
      more.disabled = true;
      more.textContent = "Preparando…";
      try {
        prompts = (await api(`/api/usar${q}`)).prompts;
        if (!alive()) return;
        i = 0;
        Object.keys(marks).forEach((k) => delete marks[k]);
        if (!prompts.length) { toast("Sem perguntas novas agora."); more.disabled = false; more.textContent = "Mais perguntas"; return; }
        show();
      } catch (e) { toast(e.message); more.disabled = false; more.textContent = "Mais perguntas"; }
    };
    clear(stage, h("h2", "Fim das perguntas"),
      h("p", { class: "soft", style: { marginTop: "8px" } },
        "O que apareceu certo aqui sobe de caixa no caderno; o que voltou errado vai para a revisão de novo. As correções novas viram cartões."),
      h("div", { class: "row section", style: { marginTop: "18px" } }, more,
        h("a", { class: "btn secondary", href: "#/conversar" }, "Conversar"), h("a", { class: "btn quiet", href: "#/hoje" }, "Voltar para hoje")));
  }

  if (!prompts.length) { done(); return () => tracker.stop(); }
  show();
  return () => { if (recorder) recorder.stop(true); tracker.stop(); };
}
