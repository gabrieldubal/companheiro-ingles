// Peças que aparecem em mais de uma tela.
import { compareButtons, playClip } from "../lib/audio.js";
import { rateBar } from "../lib/charts.js";
import { h, pct } from "../lib/dom.js";
import * as tts from "../lib/tts.js";
import { app } from "../main.js";

const VOWEL = /[aeiouæɑɒɔəɛɜɪʊʌɐᵻɚɝ]/;

/** A bancada está em duas colunas? Empilhada (celular), o apoio fica lá embaixo, depois do exercício. */
export function benchSplit(el) {
  const b = el.closest(".bench");
  return !!b && getComputedStyle(b).gridTemplateColumns.trim().split(/\s+/).length > 1;
}

/** Link para a escada de correção de uma palavra. */
export function ladderHref(tag, word, heardAs, sentence) {
  const parts = [tag, word, heardAs || "-", sentence || "-"].map((p) => encodeURIComponent(p));
  return `#/corrigir/${parts.join("/")}`;
}

/**
 * A faixa de sons: em cima o esperado, embaixo o que você fez. O som trocado fica marcado;
 * diferenças que não contam como erro (variantes de nativo) ficam com borda tracejada.
 */
export function phonemeStrip(w) {
  const offs = w.offs || [];
  const offPair = new Set(offs.map((o) => o.what.split(" (")[0]).filter((x) => x.includes("→")));
  const insertionsCount = offs.some((o) => ["ed", "final-vowel", "s-cluster"].includes(o.tag));
  const cols = [...(w.before || []).map((b) => [null, b, false]), ...(w.pairs || [])];
  const strip = h("div", { class: "strip", role: "table", "aria-label": `Sons de ${w.word}: esperado e o seu` },
    h("span", { class: "lab" }, "esperado"), h("span", { class: "lab" }, "você"));
  cols.forEach(([e, heard, same]) => {
    const key = `${e}→${heard || "∅"}`;
    const isOff = offPair.has(key) || (insertionsCount && !e && heard && VOWEL.test(heard));
    const cls = isOff ? "off" : same ? "" : "diff";
    strip.append(h("span", { class: `cell ${e ? cls : "gap " + cls}` }, e || "·"),
                 h("span", { class: `cell ${heard ? cls : "gap " + cls}` }, heard || "–"));
  });
  return strip;
}

/**
 * Raio-x de uma palavra: os sons, o que soou para um nativo, como fazer o som e os botões
 * para ouvir você, o nativo e a palavra que um nativo ouviria.
 */
export function wordXray(w, { recordingId, sentence } = {}) {
  const sounds = app.config.sounds || {};
  const offs = w.offs || [];
  const box = h("div", { class: `xray${offs.length ? "" : " good"}` });
  box.append(h("div", { class: "head" },
    h("span", { class: "w" }, w.word),
    w.sounds_like ? h("span", { class: "like" }, "Para um nativo, soou como ", h("b", w.sounds_like)) : null,
    !offs.length ? h("span", { class: "like" }, w.judged ? "Os sons saíram como o esperado." : "Esta palavra o detector não julgou.") : null));
  if (w.pairs?.length) {
    box.append(phonemeStrip(w),
      h("p", { class: "strip-legend" }, "Destacado: o som trocado. Tracejado: diferença que nativo também faz."));
  }
  if (offs.length) {
    box.append(h("ul", { class: "says" }, offs.map((o) => h("li", `${sounds[o.tag]?.label || o.tag}: ${describe(o)}.`))));
    const fix = offs.find((o) => o.fix)?.fix; // o que fazer diferente, conforme o que saiu no lugar
    if (fix) box.append(h("p", { class: "fix-line" }, fix));
  }
  const word = w.word.replace(/[^\w'-]/g, "");
  const row = h("div", { class: "row", style: { marginTop: "10px" } });
  if (recordingId && w.start != null) {
    row.append(h("button", { class: "btn secondary small", type: "button", onclick: () => playClip(recordingId, w.start, w.end) }, "▶ Você"));
    row.append(h("button", { class: "btn secondary small", type: "button",
      onclick: () => playClip(recordingId, w.start, w.end, () => setTimeout(() => tts.speak(word, 0.75), 250)) }, "▶ Você, depois o nativo"));
  }
  row.append(h("button", { class: "btn secondary small", type: "button", onclick: () => tts.speak(word, 0.75) }, `▶ Nativo: ${word}`));
  if (w.sounds_like) {
    row.append(h("button", { class: "btn secondary small", type: "button", onclick: () => tts.speak(w.sounds_like, 0.75) },
      `▶ Nativo: ${w.sounds_like}`));
  }
  box.append(row);
  if (offs.length) {
    const tag = offs[0].tag;
    const tip = sounds[tag]?.tip;
    if (tip) box.append(h("details", h("summary", { class: "soft small" }, `Como fazer o ${sounds[tag].symbol}`), tipBlock(tip)));
    box.append(h("p", { style: { marginTop: "12px" } },
      h("a", { class: "btn small", href: ladderHref(tag, word, w.sounds_like, sentence) }, "Corrigir esta palavra")));
  }
  return box;
}

/** A frase com cada palavra colorida (certa, som trocado, não julgada); clicar abre o raio-x. */
export function wordsLine(words, onPick) {
  const line = h("p", { class: "words-line" });
  words.forEach((w, i) => {
    if (i) line.append(" ");
    if (!w.judged && !w.offs?.length) { line.append(h("span", { class: "tok" }, w.word)); return; }
    const b = h("button", { class: `tok ${w.ok ? "ok" : "off"}`, type: "button",
                            title: w.ok ? "Clique para ver os sons" : "Som trocado: clique para ver o raio-x" }, w.word);
    b.onclick = () => {
      line.querySelectorAll(".tok.sel").forEach((x) => x.classList.remove("sel"));
      b.classList.add("sel");
      onPick(w);
    };
    line.append(b);
  });
  return line;
}

const STATUS_TEXT = { treinar: "para treinar", "atenção": "atenção", ok: "parecido com nativos", "pouco dado": "pouco dado" };

// "θ→s" vira "saiu s no lugar de θ"; as frases ficam em português comum.
export function describe(c) {
  const what = c.what || "";
  if (c.tag === "ed") return "ganhou uma vogal a mais no -ed";
  if (c.tag === "final-vowel") return `ganhou vogal no fim (${what.replace("+", "")})`;
  if (c.tag === "s-cluster") return "ganhou um e antes do s";
  const m = what.match(/^(.+?)→(.+)$/);
  if (!m) return what;
  const [, exp, heard] = m;
  if (heard === "∅") return `o ${exp} sumiu`;
  return `saiu ${heard} no lugar de ${exp}`;
}

// Explicação da barra, uma vez por lista (antes, cada cartão repetia a mesma frase).
export function soundLegend() {
  return h("p", { class: "legend-line" }, "A barra é quantas vezes o som saiu diferente nas suas gravações. O traço",
    h("span", { class: "tick", "aria-hidden": "true" }), "marca a taxa dos nativos.");
}

/**
 * Uma linha por som: símbolo, nome, barra, contagem e "Treinar".
 * showStatus: na lista de "Meus erros", que mistura sons bons e ruins.
 * evidence: os exemplos com a sua voz, logo abaixo da linha.
 */
export function soundRow(s, { evidence = false, showStatus = false, tip = null } = {}) {
  const more = [];
  if (evidence && s.examples?.length) {
    more.push(h("ul", { class: "evidence" }, s.examples.slice(0, 4).map((e) =>
      h("li", h("span", { class: "w" }, e.word), h("span", { class: "small soft" }, describe({ ...e, tag: s.tag })),
        compareButtons(e.word, e.recording_id, e.start, e.end),
        h("a", { class: "play", href: ladderHref(s.tag, e.word) }, "corrigir")))));
  }
  if (tip) more.push(h("details", h("summary", { class: "soft small" }, `Como fazer o ${s.symbol}`), tipBlock(tip)));
  return h("li", { class: "sound-row" },
    h("span", { class: "sym", "aria-hidden": "true" }, s.symbol),
    h("div", h("h3", s.label), h("p", { class: "ex" }, `como em ${s.example}`),
      showStatus ? h("p", { class: "status" }, STATUS_TEXT[s.status] || s.status) : null),
    h("div", { class: "meter" }, s.n >= 5 ? rateBar(s.rate, s.native, { legend: false })
                                          : h("span", { class: "small muted" }, "pouco dado ainda")),
    h("span", { class: "count" }, s.n ? `${s.off} de ${s.n}` : "nenhuma"),
    h("span", { class: "act" }, h("a", { class: "btn small secondary", href: `#/treino/${s.tag}` }, "Treinar")),
    more.length ? h("div", { class: "more" }, more) : null);
}

export function tipBlock(tip) {
  if (!tip) return null;
  return h("div", { class: "tip" },
    h("p", h("b", "Como fazer. "), tip.how),
    h("p", h("b", "O que o português costuma fazer. "), tip.trap),
    h("p", h("b", "Como conferir sozinho. "), tip.check));
}

export function rateSentence(s) {
  return s.n ? `Você trocou esse som em ${s.off} de ${s.n} vezes (${pct(s.rate)}). Nativos: ${pct(s.native)}.`
             : "Ainda não há gravações suas com esse som.";
}
