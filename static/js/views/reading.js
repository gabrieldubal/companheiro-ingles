// Leitura em voz alta: 24 frases fixas, retorno som a som e o retrato da rodada.
import { api, form } from "../lib/api.js";
import { compareButtons, playBlob } from "../lib/audio.js";
import { rateBar } from "../lib/charts.js";
import { clear, h, shortDate, toast } from "../lib/dom.js";
import { createRecorder, extFor } from "../lib/recorder.js";
import * as tts from "../lib/tts.js";
import { describe, ladderHref } from "./common.js";

export async function render(root, params) {
  if (params[0] === "rodada" && params[1]) return renderSummary(root, await api(`/api/reading/runs/${params[1]}`));
  const data = await api("/api/reading");
  const st = { runId: null, i: -1, blob: null, missed: {} };
  let recorder = null;
  const stage = h("section", { class: "stage" });
  const queue = h("ol", { class: "queue" });
  const drawQueue = () => clear(queue, data.sentences.map((x, i) =>
    h("li", { class: i === st.i ? "cur" : i < st.i && i in st.missed ? (st.missed[i] ? "miss" : "done") : "" }, h("span", { class: "serif" }, x.text))));
  root.append(h("header",
    h("p", { class: "date-line" }, h("a", { href: "#/pronuncia" }, "Pronúncia"), " / leitura"),
    h("h1", "Leitura em voz alta"),
    h("p", `${data.sentences.length} frases curtas. Leia cada uma no seu ritmo normal, antes de ouvir a versão nativa: ` +
           "a primeira leitura é o retrato de hoje. Uns 10 minutos.")),
    h("div", { class: "bench" }, h("div", { class: "bench-main" }, stage),
      h("aside", { class: "bench-side" }, h("div", { class: "side-block" }, h("h3", "As frases"), queue))));
  drawQueue();

  stage.append(h("button", { class: "btn", type: "button", onclick: (e) => { e.currentTarget.disabled = true; begin(e.currentTarget); } }, "Começar"),
    data.runs.length ? h("p", { class: "soft small", style: { marginTop: "12px" } },
      `Última rodada: ${shortDate(data.runs[0].started_at)}. `, h("a", { href: `#/leitura/rodada/${data.runs[0].id}` }, "Ver o retrato")) : null);

  async function begin(button) {
    tts.unlock();
    try {
      st.runId = (await api("/api/reading/runs", { body: {} })).run_id;
      st.i = 0;
      if (stage.isConnected) show();
    } catch (e) {
      toast(e.message);
      button.disabled = false;
    }
  }

  function show() {
    const s = data.sentences[st.i];
    const result = h("div", { class: "result" });
    recorder = createRecorder({ raw: true, idle: "Aperte espaço ou clique e leia a frase.", onBlob: (b) => record(s, b, result) });
    drawQueue();
    clear(stage,
      h("p", { class: "muted small" }, `${st.i + 1} de ${data.sentences.length}: ${s.focus_pt}`),
      h("div", { class: "progressbar" }, h("span", { style: { width: `${(100 * st.i) / data.sentences.length}%` } })),
      h("p", { class: `say${s.tags.includes("pairs") ? " pair" : ""}` }, s.text),
      recorder.el, result,
      h("div", { class: "row", style: { marginTop: "18px" } },
        h("button", { class: "btn secondary small", type: "button", onclick: () => tts.speak(s.text, 0.85) }, "▶ Ouvir nativo"),
        h("button", { class: "btn small", type: "button", onclick: (e) => next(e.currentTarget) },
          st.i < data.sentences.length - 1 ? "Próxima frase" : "Ver o retrato")));
  }

  async function record(s, blob, result) {
    st.blob = blob;
    recorder.setBusy(true, "Ouvindo os sons…");
    try {
      const r = await api(`/api/reading/runs/${st.runId}/record`, { body: form({ file: [blob, `leitura.${extFor(blob)}`], sentence_id: s.id }) });
      const off = (r.checks || []).filter((c) => !c.ok);
      st.missed[data.sentences.indexOf(s)] = off.length > 0;
      clear(result,
        r.checks?.length
          ? (off.length
              ? h("ul", { class: "verdicts" }, off.map((c) => h("li",
                  h("span", { class: "mark bad" }, "✗"),
                  h("span", { class: "serif", style: { fontSize: "1.2rem", minWidth: "6rem" } }, c.word),
                  h("span", { class: "soft" }, describe(c)),
                  compareButtons(c.word, r.recording_id, c.start, c.end),
                  h("a", { class: "play", href: ladderHref(c.tag, c.word, null, s.text) }, "corrigir"))))
              : h("p", { style: { color: "var(--mata)" } }, `✓ Os ${r.checks.length} sons que o detector olhou saíram como o esperado.`))
          : h("p", { class: "soft" }, "Não deu para julgar os sons dessa gravação. Leia a frase inteira e grave de novo."),
        h("p", { class: "small muted", style: { marginTop: "10px" } }, `O Whisper entendeu: "${r.text}"`),
        h("div", { class: "row", style: { marginTop: "10px" } },
          h("button", { class: "btn secondary small", type: "button", onclick: () => playBlob(st.blob) }, "▶ Você")));
    } catch (e) {
      toast(e.message);
    } finally {
      recorder.setBusy(false);
    }
  }

  async function next(button) {
    if (recorder) recorder.stop(true);
    if (st.i < data.sentences.length - 1) { st.i += 1; show(); return; }
    button.disabled = true; // dois cliques não podem fechar a rodada duas vezes
    try {
      const sum = await api(`/api/reading/runs/${st.runId}/finish`, { body: {} });
      if (!root.isConnected) return;
      clear(root);
      renderSummary(root, sum);
    } catch (e) {
      toast(e.message);
      button.disabled = false;
    }
  }

  return () => recorder && recorder.stop(true);
}

function renderSummary(root, sum) {
  root.append(h("header",
    h("p", { class: "date-line" }, h("a", { href: "#/pronuncia" }, "Pronúncia"), " / retrato"),
    h("h1", "Retrato da sua pronúncia"),
    h("p", `${sum.recorded} de ${sum.total} frases gravadas. Refaça daqui a um mês com as mesmas frases para ver o que mudou.`)));
  const cols = h("div", { class: "split wide-left" });
  root.append(cols);
  if (sum.by_sound?.length) {
    cols.append(h("section",
      h("h2", "Som a som"),
      h("p", { class: "soft", style: { margin: "6px 0 18px" } }, "Quantas vezes cada som saiu diferente do esperado, comparado com os nativos."),
      h("ul", { class: "list" }, sum.by_sound.map((s) => h("li",
        h("div", { class: "row", style: { justifyContent: "space-between" } },
          h("span", h("span", { class: "ipa", style: { fontSize: "1.6rem", marginRight: "12px" } }, s.symbol), s.label),
          h("span", { class: "small muted" }, `${s.off} de ${s.n}`)),
        h("div", { style: { marginTop: "8px", maxWidth: "520px" } }, rateBar(s.off / s.n, s.native)))))));
  } else {
    cols.append(h("p", { class: "empty" }, "Ainda sem análise som a som desta rodada. Ela roda em segundo plano: volte em alguns minutos."));
  }
  const flagged = sum.items.filter((i) => i.off?.length);
  if (flagged.length) {
    cols.append(h("section", { class: "section" }, h("h2", "Onde saiu diferente"),
      h("ul", { class: "list" }, flagged.map((i) => h("li",
        h("p", { class: "serif", style: { fontSize: "1.25rem" } }, i.text),
        h("ul", { class: "evidence" }, i.off.map((c) => h("li",
          h("span", { class: "w" }, c.word), h("span", { class: "small soft" }, describe(c)),
          compareButtons(c.word, i.recording_id, c.start, c.end)))))))));
  }
  root.append(h("div", { class: "row section" },
    h("a", { class: "btn", href: "#/pronuncia" }, "Ver os sons"), h("a", { class: "btn secondary", href: "#/hoje" }, "Voltar para hoje")));
}
