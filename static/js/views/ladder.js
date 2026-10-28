// Corrigir uma palavra: degraus do mais fácil ao mais difícil, 2 acertos seguidos no som sobem.
// Errou, o item fica (antes ele girava, e um item difícil zerava a sequência para sempre).
// Para destravar: a dica da troca que aconteceu, as suas tentativas com a sua voz acertando,
// um espelho na tela e, depois de 3 erros no mesmo item, o som em partes.
import { track } from "../lib/activity.js";
import { api, form } from "../lib/api.js";
import { playBlob, playClip } from "../lib/audio.js";
import { clear, h, toast } from "../lib/dom.js";
import { createRecorder, extFor } from "../lib/recorder.js";
import * as tts from "../lib/tts.js";
import { describe, phonemeStrip, tipBlock } from "./common.js";

export async function render(root, [tag, word, heardAs, sentence], alive) {
  if (!tag || !word) { location.hash = "#/pronuncia"; return; }
  const q = new URLSearchParams();
  q.set("tag", tag);
  q.set("word", word);
  if (heardAs && heardAs !== "-") q.set("heard_as", heardAs);
  if (sentence && sentence !== "-") q.set("sentence", sentence);
  const L = await api(`/api/ladder?${q}`);
  if (!alive()) return;
  const tracker = track("escada", `${tag}:${word}`);
  let state = L.state;
  let itemIdx = 0;
  let itemFails = 0; // erros seguidos neste item
  let recorder = null;
  let best = L.best; // a sua última vez com o som certo
  const attempts = [...(L.attempts || [])];
  const steps = L.steps;
  const streak = h("span", { class: "streak" });
  const mirror = createMirror();

  const stepsList = h("ol", { class: "ladder", "aria-label": "Degraus" });
  // Com espaço na tela, a dica já vem aberta ao lado; no celular, fica fechada embaixo.
  const tip = h("details", { open: matchMedia("(min-width: 1280px)").matches },
    h("summary", { class: "soft" }, `Como fazer o ${L.symbol}`), tipBlock(L.tip));
  const stage = h("section", { class: "stage" });
  const history = h("section", { class: "side-block tries-box" });
  root.append(h("header",
    h("p", { class: "date-line" }, h("a", { href: "#/pronuncia" }, "Pronúncia"), " / corrigir uma palavra"),
    h("div", { class: "row", style: { alignItems: "flex-end", gap: "22px" } },
      h("span", { class: "ipa", style: { fontSize: "4.5rem", lineHeight: ".9" }, "aria-hidden": "true" }, L.symbol),
      h("div", h("h1", L.word), h("p", { class: "soft" }, `${L.label}.`,
        L.steps.some((s) => s.key === "contra") ? ` Para um nativo, soou como ${L.heard_as}.` : ""))),
    stepsList),
    h("div", { class: "bench", style: { marginTop: "26px" } }, h("div", { class: "bench-main" }, stage),
      h("aside", { class: "bench-side" },
        h("div", { class: "side-block" }, tip),
        h("div", { class: "side-block" }, h("div", { class: "row" }, mirror.button,
          h("span", { class: "small muted" }, "A câmera na tela, para ver a língua e os lábios.")), mirror.box),
        history)));

  function drawSteps() {
    clear(stepsList, steps.map((s, i) =>
      h("li", { class: i < state.step ? "done" : i === state.step ? "cur" : "" }, s.title)));
  }

  // Logo depois do veredito, para você ver a sequência andar (ou zerar) antes de seguir.
  function drawStreak(n) {
    streak.setAttribute("aria-label", `${n} de ${L.pass_streak} acertos seguidos`);
    clear(streak, Array.from({ length: L.pass_streak }, (_, i) => h("i", { class: i < n ? "on" : "" })));
  }

  const bestButton = (label) => best
    ? h("button", { class: "btn secondary small", type: "button", onclick: () => playClip(best.recording_id, best.start, best.end) },
        label || `▶ O seu ${L.symbol} certo: ${best.word}`)
    : null;

  function drawHistory() {
    if (!attempts.length && !best) { clear(history); return; }
    clear(history,
      h("h3", "Suas tentativas"),
      best ? h("p", { class: "small soft", style: { margin: "4px 0 10px" } },
        `A sua última vez com o ${L.symbol} certo foi em "${best.word}". Ouça antes de tentar de novo: é um som que você já fez. `,
        bestButton(`▶ ${best.word}`)) : null,
      attempts.length ? h("ul", { class: "tries" }, attempts.slice(0, 10).map((a) => h("li",
        h("span", { class: `mark ${a.ok ? "good" : "bad"}` }, a.ok ? "✓" : "✗"),
        h("span", { class: "serif" }, a.text),
        h("span", { class: "small soft" }, a.ok ? "certo" : describe(a)),
        a.start != null ? h("button", { class: "play", type: "button", onclick: () => playClip(a.recording_id, a.start, a.end) }, `▶ ${a.word}`) : null)))
        : null);
  }

  function show() {
    drawSteps();
    if (state.mastered_at && state.step >= steps.length) { done(); return; }
    const s = steps[Math.min(state.step, steps.length - 1)];
    const it = s.items[itemIdx % s.items.length];
    const result = h("div", { class: "result" });
    recorder = createRecorder({ raw: true, idle: "Aperte espaço ou clique e diga em voz alta.", onBlob: (b) => attempt(s, it, b, result) });
    drawStreak(state.streak);
    const stuck = itemFails >= 3;
    const parts = L.parts?.[it.targets[0]] || L.parts?.[L.word.toLowerCase()] || [];
    clear(stage,
      h("h2", s.title),
      h("p", { class: "soft", style: { marginTop: "6px" } }, s.help),
      h("p", { class: "say" }, it.text),
      h("div", { class: "row" },
        h("button", { class: "btn secondary small", type: "button", onclick: () => tts.speak(it.text, 0.7) }, "▶ Ouvir nativo, devagar"),
        h("span", { class: "small soft" }, "Acertos seguidos:", streak),
        s.items.length > 1 ? h("button", { class: "btn quiet small", type: "button", onclick: () => { itemIdx += 1; itemFails = 0; show(); } },
          "Trocar de item") : null),
      recorder.el, result,
      stuck && parts.length ? h("div", { class: "tip parts" },
        h("p", h("b", "Três erros seguidos neste item. Vamos por partes. "),
          "Sem gravar: faça cada passo umas três vezes, de preferência no espelho, e depois grave o item de novo."),
        h("ol", parts.map((p) => h("li", p)))) : null,
      stuck && state.step > 0 ? h("p", { style: { marginTop: "12px" } },
        h("button", { class: "btn small secondary", type: "button", onclick: stepDown }, "Voltar um degrau")) : null);
    if (stuck) tip.open = true;
  }

  async function attempt(s, it, blob, result) {
    recorder.setBusy(true, "Ouvindo o som…");
    tracker.bump();
    try {
      const r = await api("/api/ladder/attempt", { body: form({
        file: [blob, `escada.${extFor(blob)}`], tag, word: L.word, text: it.text,
        targets: JSON.stringify(it.targets), steps: String(steps.length),
      }) });
      if (!alive()) return;
      const words = r.words.filter((w) => it.targets.includes(w.word.toLowerCase()));
      if (!r.judged) {
        clear(result, h("p", { class: "soft" }, r.pron === "pronto"
          ? "Não deu para julgar o som: diga o item inteiro, sem pausa longa no meio, num volume normal, e grave de novo."
          : `Detector de pronúncia: ${r.pron}.`),
          h("p", { class: "small muted" }, `O Whisper entendeu: "${r.text}"`));
        return;
      }
      state = r.state;
      if (r.attempt) {
        attempts.unshift(r.attempt);
        if (r.ok && r.attempt.start != null) best = { ...r.attempt };
        drawHistory();
      }
      // Acertou: o próximo item. Errou: o mesmo item, até sair.
      if (r.ok) { itemIdx += 1; itemFails = 0; } else { itemFails += 1; }
      drawStreak(r.state.advanced ? L.pass_streak : r.state.streak);
      if (r.state.advanced) drawSteps();
      const verdicts = h("ul", { class: "verdicts" }, r.target.map((c) => h("li",
        h("span", { class: `mark ${c.ok ? "good" : "bad"}` }, c.ok ? "✓" : "✗"),
        h("span", { class: "serif", style: { fontSize: "1.2rem", minWidth: "6rem" } }, c.word),
        h("span", { class: "soft" }, c.ok ? "o som saiu certo" : describe(c)))));
      const fixes = [...new Set(r.target.filter((c) => !c.ok && c.fix).map((c) => c.fix))];
      // Sem pular sozinho: você lê o veredito e a faixa de sons no seu tempo e segue quando quiser.
      const label = r.state.just_mastered ? "Ver o resultado" : r.state.advanced ? "Ir para o próximo degrau"
        : r.ok ? "Próximo item" : "Tentar de novo";
      if (r.state.advanced) itemIdx = 0;
      clear(result,
        r.state.advanced && !r.state.just_mastered ? h("p", { style: { color: "var(--mata)", fontWeight: 700 } }, `Degrau vencido: ${s.title}.`) : null,
        verdicts,
        fixes.length ? h("div", { class: "tip fix-tip" }, fixes.map((f) => h("p", f))) : null,
        words.map((w) => phonemeStrip(w)),
        h("div", { class: "row", style: { marginTop: "10px" } },
          h("button", { class: "btn secondary small", type: "button", onclick: () => playBlob(blob) }, "▶ Você agora"),
          r.ok ? null : bestButton(),
          h("button", { class: "btn secondary small", type: "button", onclick: () => tts.speak(it.text, 0.7) }, "▶ Nativo"),
          h("button", { class: "btn small", type: "button", onclick: () => (r.state.just_mastered ? done() : show()) }, label)));
    } catch (e) {
      toast(e.message);
    } finally {
      recorder.setBusy(false);
    }
  }

  async function stepDown() {
    try {
      state = { ...state, ...(await api("/api/ladder/step", { body: { tag, word: L.word, step: state.step - 1 } })) };
      itemIdx = 0;
      itemFails = 0;
      show();
    } catch (e) { toast(e.message); }
  }

  function done() {
    drawSteps();
    clear(stage,
      h("h2", "Palavra corrigida"),
      h("p", { class: "soft", style: { marginTop: "8px" } },
        `Você subiu todos os degraus do ${L.symbol} em "${L.word}". Ela sai da lista de palavras para corrigir. ` +
        "Se o som voltar a sair trocado numa frase ou conversa, ela volta para a lista e a escada recomeça."),
      h("div", { class: "row section", style: { marginTop: "22px" } },
        h("a", { class: "btn", href: `#/usar/som/${tag}` }, "Usar o som numa resposta"),
        h("a", { class: "btn secondary", href: "#/imitar" }, "Imitar um texto"),
        h("a", { class: "btn quiet", href: "#/pronuncia" }, "Outras palavras")));
  }

  drawHistory();
  show();
  return () => { if (recorder) recorder.stop(true); mirror.stop(); tracker.stop(); };
}

// Espelho: a câmera do computador na tela, invertida como um espelho. Nada é gravado nem enviado.
// Serve para ver a língua entre os dentes (θ, ð), a ponta da língua no l e o lábio que vira f.
function createMirror() {
  let stream = null;
  const video = h("video", { autoplay: true, muted: true, playsinline: true });
  const box = h("div", { class: "mirror", hidden: true }, video,
    h("p", { class: "small muted" }, "Só na tela: nada é gravado. No θ você tem que ver a ponta da língua entre os dentes, e o lábio de baixo solto."));
  const button = h("button", { class: "btn secondary small", type: "button" }, "Espelho");
  async function start() {
    try {
      stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "user", width: { ideal: 640 } }, audio: false });
      video.srcObject = stream;
      box.hidden = false;
      button.textContent = "Fechar o espelho";
    } catch {
      toast("Não consegui abrir a câmera. Veja se o navegador tem permissão para usá-la.");
    }
  }
  function stop() {
    if (stream) stream.getTracks().forEach((t) => t.stop());
    stream = null;
    video.srcObject = null;
    box.hidden = true;
    button.textContent = "Espelho";
  }
  button.onclick = () => (stream ? stop() : start());
  return { button, box, stop };
}
