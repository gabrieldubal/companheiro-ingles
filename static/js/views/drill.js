// Treino de som: um som só, itens curtos, retorno som a som em cada palavra-alvo.
import { track } from "../lib/activity.js";
import { api, form } from "../lib/api.js";
import { playBlob } from "../lib/audio.js";
import { bare, clear, h, plural, toast } from "../lib/dom.js";
import { createRecorder, extFor } from "../lib/recorder.js";
import * as tts from "../lib/tts.js";
import { describe, ladderHref, rateSentence, tipBlock } from "./common.js";

export async function render(root, [tag]) {
  if (!tag) { location.hash = "#/pronuncia"; return; }
  const d = await api(`/api/drills/${tag}`);
  const tracker = track("treino", tag);
  const state = { i: 0, results: [], blob: null };
  let recorder = null;

  const header = h("header",
    h("p", { class: "date-line" }, h("a", { href: "#/pronuncia" }, "Pronúncia"), " / treino"),
    h("div", { class: "row", style: { alignItems: "flex-end", gap: "22px" } },
      h("span", { class: "ipa", style: { fontSize: "5.5rem", lineHeight: ".9" }, "aria-hidden": "true" }, d.symbol),
      h("div", h("h1", d.label), h("p", { class: "soft" }, `Como em ${d.example}.`))),
    d.pron !== "pronto" ? h("p", { class: "muted small" }, `Detector de pronúncia: ${d.pron}. Sem ele, o treino só compara as palavras.`) : null);

  // Ao lado do exercício: como fazer o som e como você está nele.
  const side = h("aside", { class: "bench-side" },
    h("div", { class: "side-block" }, h("h3", "Como fazer esse som"), tipBlock(d.tip),
      d.listen ? h("p", { class: "small", style: { marginTop: "10px" } }, "Ainda não escuta a diferença? ",
        h("a", { href: `#/ouvir/${tag}` }, "Treine o ouvido primeiro")) : null),
    d.profile ? h("div", { class: "side-block" }, h("h3", "Você nesse som"), h("p", { class: "soft small" }, rateSentence(d.profile))) : null);
  const stage = h("section", { class: "stage" });
  root.append(header, h("div", { class: "bench section", style: { marginTop: "26px" } }, h("div", { class: "bench-main" }, stage), side));

  function targetsMarked(item) {
    const want = new Set(item.targets.map((t) => t.toLowerCase()));
    const p = h("p", { class: `say${item.text.includes(",") && !item.text.endsWith(".") ? " pair" : ""}` });
    item.text.split(" ").forEach((w, i) => {
      if (i) p.append(" ");
      p.append(want.has(bare(w).toLowerCase()) ? h("span", { style: { textDecoration: "underline 2px var(--ipe)", textUnderlineOffset: "6px" } }, w) : w);
    });
    return p;
  }

  function showItem() {
    const item = d.items[state.i];
    const result = h("div", { class: "result" });
    const skip = h("div", { class: "row section", style: { marginTop: "18px" } },
      h("button", { class: "btn quiet", type: "button", onclick: next }, state.i < d.items.length - 1 ? "Pular" : "Terminar"));
    recorder = createRecorder({ raw: true, idle: "Aperte espaço ou clique e leia em voz alta.",
                                onBlob: (b) => attempt(item, b, result, skip) });
    clear(stage,
      h("p", { class: "muted small" }, `Item ${state.i + 1} de ${d.items.length}. As palavras sublinhadas são as que o detector vai olhar.`),
      h("div", { class: "progressbar" }, h("span", { style: { width: `${(100 * state.i) / d.items.length}%` } })),
      targetsMarked(item),
      h("div", { class: "row" },
        h("button", { class: "btn secondary small", type: "button", onclick: () => tts.speak(item.text, 0.8) }, "▶ Ouvir nativo, devagar")),
      recorder.el, result, skip);
  }

  async function attempt(item, blob, result, skip) {
    const index = state.i; // se você pular no meio da análise, o resultado continua sendo deste item
    state.blob = blob;
    recorder.setBusy(true, "Ouvindo os sons…");
    tracker.bump();
    try {
      const r = await api(`/api/drills/${tag}/attempt`, {
        body: form({ file: [blob, `treino.${extFor(blob)}`], text: item.text, targets: JSON.stringify(item.targets) }),
      });
      const good = r.target.filter((c) => c.ok).length;
      state.results[index] = { good, total: r.target.length };
      if (index !== state.i || !result.isConnected) return; // já está em outro item
      skip.hidden = true;
      clear(result,
        r.target.length
          ? h("ul", { class: "verdicts" }, r.target.map((c) =>
              h("li", h("span", { class: `mark ${c.ok ? "good" : "bad"}` }, c.ok ? "✓" : "✗"),
                h("span", { class: "serif", style: { fontSize: "1.2rem", minWidth: "6rem" } }, c.word),
                h("span", { class: "soft" }, c.ok ? "certo" : describe(c)),
                h("button", { class: "play", type: "button", onclick: () => tts.speak(c.word, 0.8) }, "▶ nativo"),
                c.ok ? null : h("a", { class: "play", href: ladderHref(tag, c.word, null, item.text) }, "corrigir"))))
          : h("p", { class: "soft" }, r.pron === "pronto"
              ? "Não deu para julgar: o detector não achou as palavras-alvo nessa gravação. Leia o item inteiro e grave de novo."
              : "Sem o detector de pronúncia, só dá para comparar as palavras."),
        h("p", { class: "small muted", style: { marginTop: "10px" } }, `O Whisper entendeu: "${r.text}"`),
        h("div", { class: "row", style: { marginTop: "12px" } },
          h("button", { class: "btn secondary small", type: "button", onclick: () => playBlob(state.blob) }, "▶ Você"),
          h("button", { class: "btn secondary small", type: "button", onclick: () => tts.speak(item.text, 0.8) }, "▶ Nativo"),
          h("button", { class: "btn small", type: "button", onclick: next }, state.i < d.items.length - 1 ? "Próximo item" : "Ver o resultado")));
    } catch (e) {
      toast(e.message);
    } finally {
      recorder.setBusy(false);
    }
  }

  function next() {
    if (recorder) recorder.stop(true);
    if (state.i < d.items.length - 1) { state.i += 1; showItem(); return; }
    finish();
  }

  function finish() {
    const done = state.results.filter(Boolean);
    const good = done.reduce((a, r) => a + r.good, 0);
    const total = done.reduce((a, r) => a + r.total, 0);
    const gen = h("button", { class: "btn secondary", type: "button" }, "Gerar frases do meu mundo");
    gen.onclick = async () => {
      gen.disabled = true;
      gen.textContent = "Pedindo ao Claude…";
      try {
        const r = await api(`/api/drills/${tag}/generate`, { body: {} });
        toast(`${plural(r.items.length, "frase nova", "frases novas")} no próximo treino.`);
        gen.textContent = "Frases prontas para o próximo treino";
      } catch (e) {
        toast(e.message);
        gen.disabled = false;
        gen.textContent = "Gerar frases do meu mundo";
      }
    };
    clear(stage,
      h("h2", total ? `${good} de ${total} certos` : "Treino terminado"),
      h("p", { class: "soft", style: { marginTop: "8px" } }, total
        ? "Cada tentativa entra na conta do som em Meus erros e no Progresso. A melhora aparece em semanas, não num treino."
        : "Nenhum item foi gravado desta vez."),
      h("div", { class: "row section", style: { marginTop: "22px" } },
        h("button", { class: "btn", type: "button", onclick: () => { state.i = 0; state.results = []; showItem(); } }, "Mais uma rodada"),
        gen,
        h("a", { class: "btn quiet", href: "#/hoje" }, "Voltar para hoje")));
  }

  showItem();
  return () => { if (recorder) recorder.stop(true); tracker.stop(); };
}
