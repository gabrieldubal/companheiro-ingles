// Meus erros: pronúncia (com a sua voz como prova), gramática (com as suas frases) e palavras novas.
import { api } from "../lib/api.js";
import { clear, h, plural, shortDate } from "../lib/dom.js";
import * as tts from "../lib/tts.js";
import { soundLegend, soundRow } from "./common.js";

function boxes(n) {
  return h("span", { class: "boxes", title: `caixa ${n} de 5`, "aria-label": `caixa ${n} de 5` },
    [1, 2, 3, 4, 5].map((i) => h("i", { class: i <= n ? "on" : "" })));
}

function soundsTab(e) {
  const withData = e.sounds.filter((s) => s.n > 0);
  if (!withData.length) {
    return h("div", { class: "empty" }, h("p", "Ainda sem medidas de pronúncia."),
      h("a", { class: "btn", href: "#/leitura" }, "Fazer a leitura em voz alta"));
  }
  return h("div",
    h("p", { class: "soft", style: { marginBottom: "10px" } },
      "Cada exemplo é um trecho da sua gravação: ouça você e ouça o nativo, um depois do outro."),
    soundLegend(),
    h("ul", { class: "sound-list cols" }, withData.map((s) => soundRow(s, {
      evidence: true, showStatus: true,
      tip: s.status === "treinar" || s.status === "atenção" ? s.tip : null,
    }))));
}

function grammarTab(e) {
  if (!e.grammar.length) {
    return h("div", { class: "empty" }, h("p", "Ainda sem erros de gramática anotados. Eles aparecem conforme você conversa."),
      h("a", { class: "btn", href: "#/conversar" }, "Conversar"));
  }
  const due = e.grammar.filter((g) => g.due).length;
  return h("div",
    h("div", { class: "row", style: { justifyContent: "space-between", marginBottom: "12px" } },
      h("p", { class: "soft" }, due ? `${plural(due, "padrão está", "padrões estão")} na hora de revisar.` : "Nada na hora de revisar agora."),
      due ? h("a", { class: "btn", href: "#/fale-certo" }, "Fazer o Fale certo") : null),
    h("ul", { class: "grid-list", style: { "--col": "520px" } }, e.grammar.map((g) => h("li", { class: "pattern" },
      h("div", h("h3", g.label), h("p", { class: "small muted" },
        `${plural(g.count, "vez", "vezes")}, acertou ${plural(g.good_uses, "vez", "vezes")} na revisão. Visto em ${shortDate(g.last_seen)}.`)),
      h("div", { class: "row" }, g.due ? h("span", { class: "chip treinar" }, "revisar") : null, boxes(g.box),
        h("a", { class: "play", href: `#/entender/${encodeURIComponent(`padrao:${g.pattern}`)}` }, "Entender"),
        h("a", { class: "play", href: `#/perguntar/${encodeURIComponent(`Me explica "${g.label}" usando os meus erros, e cria cartões para eu revisar.`)}` },
          "Perguntar")),
      h("div", { class: "ex" }, g.examples.slice(0, 2).map((x) => h("div", { style: { marginTop: "6px" } },
        h("p", { class: "line" }, h("del", x.original), "  ", h("ins", x.better), " ",
          h("button", { class: "play", type: "button", onclick: () => tts.speak(x.better) }, "▶")),
        x.explanation_pt ? h("p", { class: "small soft" }, x.explanation_pt) : null)))))));
}

function wordsTab(e) {
  if (!e.words.length) return h("div", { class: "empty" }, h("p", "As palavras novas que o tutor sugere aparecem aqui."));
  return h("ul", { class: "grid-list", style: { "--col": "360px" } }, e.words.map((w) => h("li",
    h("p", h("b", { class: "serif", style: { fontSize: "1.2rem" } }, w.word), "  ", w.meaning_pt, " ",
      h("button", { class: "play", type: "button", onclick: () => tts.speak(`${w.word}. ${w.example}`) }, "▶")),
    h("p", { class: "soft serif", style: { fontStyle: "italic" } }, w.example))));
}

export async function render(root, [tab]) {
  const e = await api("/api/errors");
  const tabs = { pronuncia: ["Pronúncia", soundsTab], gramatica: ["Gramática", grammarTab], palavras: ["Palavras novas", wordsTab] };
  const current = tabs[tab] ? tab : "pronuncia";
  const body = h("div");
  const bar = h("div", { class: "tabs", role: "tablist" }, Object.entries(tabs).map(([key, [label]]) =>
    h("button", { type: "button", role: "tab", "aria-selected": key === current ? "true" : "false",
                  onclick: () => (location.hash = `#/erros/${key}`) }, label)));
  root.append(h("header", h("h1", "Meus erros"),
    h("p", "Tudo o que o app anotou sobre a sua fala, com prova: a sua gravação, a sua frase, o número de vezes.")), bar, body);
  clear(body, tabs[current][1](e));
}
