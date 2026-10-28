// Fale certo: um erro seu da conversa por vez. Você diz a versão certa em voz alta;
// acertar sobe o padrão de caixa (volta mais tarde), errar mantém na caixa 1.
import { track } from "../lib/activity.js";
import { api, form } from "../lib/api.js";
import { playBlob } from "../lib/audio.js";
import { clear, collapseRepeats, h, plural, toast } from "../lib/dom.js";
import { createRecorder, extFor } from "../lib/recorder.js";
import * as tts from "../lib/tts.js";

function tokens(cmp) {
  const p = h("p", { class: "say", style: { fontSize: "1.6rem" } });
  cmp.tokens.forEach((t, i) => {
    if (i) p.append(" ");
    p.append(t.status === "diff" ? h("span", { class: "tok-off", title: t.heard ? `ouviu: ${t.heard}` : "" }, t.w) : t.w);
  });
  return p;
}

// A resposta com as palavras que a correção trouxe em negrito: é nelas que o erro estava.
function markChanged(it) {
  const set = new Set(it.changed || []);
  const p = [];
  it.better.split(" ").forEach((w, i) => { if (i) p.push(" "); p.push(set.has(i) ? h("b", { class: "changed" }, w) : w); });
  return p;
}

// O veredito diz o que foi corrigido e o que ficou: "needed" certo, mas "journey" ainda lá.
function verdictLines(r, retry) {
  const q = (ws) => ws.map((w) => `"${w}"`).join(", ");
  const parts = [];
  if (r.kept?.length) parts.push(`Ainda saiu ${q(r.kept)}, que era parte do erro.`);
  if (r.missing?.length) parts.push(`Faltou ${q(r.missing)}.`);
  if (!r.ok && r.fixed?.length) parts.push(`${q(r.fixed)} saiu certo.`);
  return [
    h("h3", { style: { color: r.ok ? "var(--mata)" : "var(--pitaya)" } },
      r.ok ? "Isso. Esse erro volta só daqui a alguns dias." : `Quase. ${retry}`),
    parts.length ? h("p", { style: { marginTop: "6px" } }, parts.join(" ")) : null,
    // Diferenças aparecem mesmo no acerto: uma palavra trocada que não era o erro também merece um olho.
    r.compare?.diffs ? h("div", h("p", { class: "soft small" }, r.ok ? "Ficou diferente, mas não muda o erro:" : "Onde ficou diferente:"),
      tokens(r.compare)) : null,
  ];
}

export async function render(root, [mode]) {
  const { items } = await api("/api/practice");
  const typing = mode === "escrever"; // onde não dá para falar: escreve a versão certa
  root.append(h("header", h("h1", typing ? "Fale certo, por escrito" : "Fale certo"),
    h("p", typing
      ? "Frases que você disse nas conversas, com um erro dentro. Escreva a versão certa sem olhar a resposta. Conta como a revisão falada."
      : "Frases que você disse nas conversas, com um erro dentro. Leia o que você disse e fale a versão certa em voz alta, sem olhar a resposta."),
    h("p", { class: "small" }, h("a", { href: typing ? "#/fale-certo" : "#/fale-certo/escrever" },
      typing ? "Posso falar agora" : "Não posso falar agora: escrever"))));
  if (!items.length) {
    root.append(h("div", { class: "empty" },
      h("p", "Nada para revisar agora. Os erros voltam aqui no dia certo, conforme você conversa."),
      h("a", { class: "btn", href: "#/conversar" }, "Conversar")));
    return;
  }
  const tracker = track("fale-certo");
  const stage = h("section", { class: "stage" });
  // Ao lado: a fila do dia (o que você queria dizer em cada uma) e quantas saíram certas.
  const queue = h("ol", { class: "queue" });
  const score = h("p", { class: "small soft" });
  root.append(h("div", { class: "bench" }, h("div", { class: "bench-main" }, stage),
    h("aside", { class: "bench-side" }, h("div", { class: "side-block" }, h("h3", "A revisão de hoje"), score, queue))));
  const state = { i: 0, ok: 0, done: 0, marks: {} };
  let recorder = null;

  function drawQueue() {
    score.textContent = state.done ? `${state.ok} de ${state.done} certas até agora.` : `${plural(items.length, "frase", "frases")} para dizer do jeito certo.`;
    clear(queue, items.map((x, i) => h("li", { class: state.marks[i] || (i === state.i ? "cur" : "") },
      h("span", { class: "serif" }, x.meaning_pt || collapseRepeats(x.original)), h("span", { class: "sub" }, x.label))));
  }

  function show() {
    const it = items[state.i];
    drawQueue();
    const answer = h("div", { hidden: true },
      h("p", { class: "say answer-line", style: { fontSize: "1.6rem", color: "var(--mata)" } }, markChanged(it)),
      it.explanation_pt ? h("p", { class: "soft" }, it.explanation_pt) : null);
    const result = h("div", { class: "result" });
    recorder = typing ? null
      : createRecorder({ raw: false, idle: "Aperte espaço ou clique e diga a versão certa.", onBlob: (b) => attempt(it, b, result, answer) });
    // O que você queria dizer é a tarefa; a sua frase, com o trecho errado marcado, mostra onde mexer.
    clear(stage,
      h("p", { class: "muted small" }, `${state.i + 1} de ${items.length}`),
      h("div", { class: "progressbar" }, h("span", { style: { width: `${(100 * state.i) / items.length}%` } })),
      it.context?.asked ? h("p", { class: "small muted" }, `Na conversa, a pergunta era: "${it.context.asked}"`) : null,
      it.meaning_pt ? [h("p", { class: "soft", style: { marginTop: "10px" } }, "Você queria dizer:"),
                       h("p", { class: "meaning" }, it.meaning_pt)] : null,
      h("p", { class: "soft", style: { marginTop: "12px" } }, "Você disse:"),
      saidLine(it),
      h("p", { class: "small soft", style: { marginTop: "6px" } },
        `Diga em inglês, do jeito certo, ${it.context ? "o trecho marcado" : "essa frase"}. Dica: o erro é de ${it.label}.`),
      typing ? typedBox(it, result, answer) : recorder.el, result,
      h("div", { class: "row", style: { marginTop: "16px" } },
        h("button", { class: "btn quiet", type: "button", onclick: () => (answer.hidden = !answer.hidden) }, "Ver a resposta"),
        h("button", { class: "btn quiet", type: "button", onclick: next }, state.i < items.length - 1 ? "Pular" : "Terminar")),
      answer);
  }

  function saidLine(it) {
    const c = it.context;
    if (!c) return h("p", { class: "said" }, collapseRepeats(it.original));
    return h("p", { class: "said-ctx" }, c.cut_start ? "… " : "", collapseRepeats(c.before), " ",
      h("mark", collapseRepeats(c.match)), " ", collapseRepeats(c.after), c.cut_end ? " …" : "");
  }

  function typedBox(it, result, answer) {
    const box = h("textarea", { rows: 2, placeholder: "Escreva a versão certa e aperte Enter", "aria-label": "A versão certa" });
    const btn = h("button", { class: "btn", type: "button" }, "Conferir");
    const go = async () => {
      if (!box.value.trim() || btn.disabled) return;
      btn.disabled = true;
      tracker.bump();
      const idx = state.i;
      try {
        const r = await api("/api/practice/typed", { body: { mistake_id: it.mistake_id, pattern: it.pattern, target: it.better, text: box.value } });
        state.done += 1;
        if (r.ok) state.ok += 1;
        state.marks[idx] = r.ok ? "done" : "miss";
        drawQueue();
        if (!result.isConnected) return;
        answer.hidden = false;
        box.disabled = true;
        clear(result, ...verdictLines(r, "Compare com a resposta acima."),
          h("div", { class: "row", style: { marginTop: "12px" } },
            h("button", { class: "btn secondary small", type: "button", onclick: () => tts.speak(it.better) }, "▶ Nativo"),
            h("button", { class: "btn small", type: "button", onclick: next }, state.i < items.length - 1 ? "Próximo" : "Terminar")));
      } catch (e) {
        toast(e.message);
        btn.disabled = false;
      }
    };
    btn.onclick = go;
    box.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); go(); } });
    setTimeout(() => box.focus(), 0);
    return h("div", { class: "typed-answer" }, box, btn);
  }

  async function attempt(it, blob, result, answer) {
    recorder.setBusy(true, "Conferindo…");
    tracker.bump();
    const idx = state.i;
    try {
      const r = await api("/api/practice/attempt", {
        body: form({ file: [blob, `fala.${extFor(blob)}`], mistake_id: it.mistake_id, pattern: it.pattern, target: it.better }),
      });
      state.done += 1;
      if (r.ok) state.ok += 1;
      state.marks[idx] = r.ok ? "done" : "miss";
      drawQueue();
      if (!result.isConnected) return; // já passou para o próximo item
      answer.hidden = false;
      clear(result, ...verdictLines(r, "Compare com a resposta e tente de novo."),
        h("p", { class: "small muted" }, `O Whisper entendeu: "${r.text}"`),
        h("div", { class: "row", style: { marginTop: "12px" } },
          h("button", { class: "btn secondary small", type: "button", onclick: () => playBlob(blob) }, "▶ Você"),
          h("button", { class: "btn secondary small", type: "button", onclick: () => tts.speak(it.better) }, "▶ Nativo"),
          h("button", { class: "btn small", type: "button", onclick: next }, state.i < items.length - 1 ? "Próximo" : "Terminar")));
    } catch (e) {
      toast(e.message);
    } finally {
      recorder.setBusy(false);
    }
  }

  function next() {
    if (recorder) recorder.stop(true);
    if (state.i < items.length - 1) { state.i += 1; show(); return; }
    state.i = items.length;
    drawQueue();
    clear(stage,
      h("h2", state.done ? `${state.ok} de ${plural(state.done, "frase certa", "frases certas")}` : "Revisão terminada"),
      h("p", { class: "soft", style: { marginTop: "8px" } },
        "Os que você acertou sobem de caixa e voltam mais tarde. Os outros voltam na próxima revisão."),
      h("p", { class: "soft", style: { marginTop: "8px" } },
        "Acertar lendo é metade. O teste é a correção aparecer quando você fala à vontade."),
      h("div", { class: "row section", style: { marginTop: "22px" } },
        h("a", { class: "btn", href: "#/usar" }, "Agora com as suas palavras"),
        h("a", { class: "btn secondary", href: "#/hoje" }, "Voltar para hoje"),
        h("a", { class: "btn quiet", href: "#/erros" }, "Ver meus erros")));
  }

  show();
  return () => { if (recorder) recorder.stop(true); tracker.stop(); };
}
