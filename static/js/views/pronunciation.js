// Pronúncia: os sons em lista, do que mais precisa de treino ao que já está bom, e a leitura em voz alta.
import { api } from "../lib/api.js";
import { h, plural, shortDate } from "../lib/dom.js";
import { ladderHref, soundLegend, soundRow } from "./common.js";

export async function render(root) {
  const [e, r, pw] = await Promise.all([api("/api/errors"), api("/api/reading"), api("/api/problem-words")]);
  const open = pw.words.filter((w) => !w.mastered);
  const train = e.sounds.filter((s) => s.status === "treinar" || s.status === "atenção");
  const ok = e.sounds.filter((s) => s.status === "ok");
  const few = e.sounds.filter((s) => s.status === "pouco dado");

  root.append(h("header", h("h1", "Pronúncia"),
    h("p", "O detector ouve os sons que você produziu e compara com o esperado, som a som. Ele só marca um som " +
           "para treinar quando a sua taxa fica bem acima da dos nativos, medida em 214 falas de americanos.")));
  if (e.pron !== "pronto") root.append(h("p", { class: "empty" }, `Detector de pronúncia: ${e.pron}.`));

  // Os três treinos lado a lado; embaixo, duas colunas: as palavras e a leitura, os sons.
  const tool = (btn, text) => h("div", btn, h("span", { class: "soft small" }, text));
  root.append(h("div", { class: "tools" },
    tool(h("a", { class: "btn", href: "#/frases" }, "Frases para falar"), "Frases com os seus sons fracos, com raio-x de cada palavra trocada."),
    tool(h("a", { class: "btn secondary", href: "#/ouvir" }, "Ouvir a diferença"), "Pares como ship e sheep em vozes diferentes: você escolhe qual ouviu."),
    tool(h("a", { class: "btn secondary", href: "#/imitar" }, "Imitar"), "Textos curtos: ouça o nativo e repita no mesmo ritmo. Mede os sons e o tempo.")));
  const left = h("div");
  const right = h("div");
  root.append(h("div", { class: "split" }, left, right));

  if (open.length) {
    left.append(h("section",
      h("h2", "Palavras para corrigir"),
      h("p", { class: "soft", style: { margin: "6px 0 14px" } },
        "Palavras em que um som saiu trocado, das mais frequentes às mais raras. Cada uma tem uma escada curta de correção."),
      h("ul", { class: "list" }, open.slice(0, 12).map((w) => h("li", { class: "row", style: { justifyContent: "space-between" } },
        h("span",
          h("b", { class: "serif", style: { fontSize: "1.25rem", marginRight: "10px" } }, w.word),
          h("span", { class: "soft small" }, `${w.label}, ${w.misses} ${w.misses === 1 ? "vez" : "vezes"}`),
          w.heard_as ? h("span", { class: "soft small" }, `, soou como ${w.heard_as}`) : null,
          w.step ? h("span", { class: "small muted" }, `, no degrau ${w.step + 1}`) : null),
        h("a", { class: "btn small secondary", href: ladderHref(w.tag, w.word, w.heard_as, w.sentence) }, w.step ? "Continuar" : "Corrigir")))),
      open.length > 12 ? h("p", { class: "small muted", style: { marginTop: "8px" } }, `E mais ${open.length - 12}.`) : null));
  }

  right.append(h("section",
    h("h2", train.length ? "Para treinar" : "Nada para treinar ainda"),
    h("p", { class: "soft", style: { margin: "6px 0 14px" } }, train.length
      ? "Na ordem do que mais atrapalha para ser entendido."
      : "Faça a leitura em voz alta ou converse com os áudios guardados para o detector ter o que medir."),
    train.length ? [soundLegend(), h("ul", { class: "sound-list" }, train.map((s) => soundRow(s)))] : null));

  left.append(h("section", { class: "section" },
    h("h2", "Leitura em voz alta"),
    h("p", "As mesmas 24 frases de sempre, com os sons difíceis para quem fala português. Refaça uma vez por mês e compare."),
    h("a", { class: "btn", href: "#/leitura", style: { marginTop: "12px" } }, r.runs.length ? "Fazer outra rodada" : "Fazer a primeira rodada"),
    r.runs.length ? h("ul", { class: "list", style: { marginTop: "18px" } }, r.runs.map((run) =>
      h("li", { class: "row", style: { justifyContent: "space-between" } },
        h("span", `${shortDate(run.started_at)}: ${plural(run.recorded, "frase", "frases")} de ${r.sentences.length}`),
        h("a", { class: "btn quiet", href: `#/leitura/rodada/${run.id}` }, "Ver o retrato")))) : null));

  if (ok.length) {
    right.append(h("section", { class: "section" }, h("h2", "Já está bom"),
      h("p", "Taxa parecida com a dos nativos. Continua sendo medido."),
      h("ul", { class: "sound-list" }, ok.map((s) => soundRow(s)))));
  }
  if (few.length) {
    right.append(h("section", { class: "section" }, h("h2", "Pouco dado"),
      h("p", "Menos de 5 checagens: ainda não dá para dizer nada. Dá para treinar mesmo assim."),
      h("div", { class: "row" }, few.map((s) => h("a", { class: "chip", href: `#/treino/${s.tag}` }, `${s.symbol} ${s.label}`)))));
  }
}
