// Histórico: conversas (com o resumo) e rodadas de leitura.
import { api } from "../lib/api.js";
import { h, plural, shortDate } from "../lib/dom.js";
import { app } from "../main.js";

export async function render(root) {
  const [history, reading] = await Promise.all([api("/api/history"), api("/api/reading")]);
  const sessions = history.sessions.filter((s) => s.student_turns > 0); // abertas e abandonadas não contam
  const titles = Object.fromEntries(app.config.scenarios.map((s) => [s.id, s.title]));
  const cols = h("div", { class: "split wide-left" });
  root.append(h("header", h("h1", "Histórico")), cols);
  cols.append(h("section", h("h2", "Conversas"),
    sessions.length ? h("ul", { class: "list", style: { marginTop: "14px" } }, sessions.map((s) => {
      const sum = s.summary;
      return h("li",
        h("div", { class: "row", style: { justifyContent: "space-between" } },
          h("strong", titles[s.scenario] || s.scenario),
          h("span", { class: "small muted" }, `${shortDate(s.started_at)}, ${plural(s.student_turns, "resposta", "respostas")}`)),
        sum?.cefr_estimate ? h("p", { class: "small soft" }, `Nível estimado: ${sum.cefr_estimate}`) : null,
        sum ? h("details", h("summary", { class: "small soft" }, "Resumo"),
          h("p", { style: { marginTop: "8px" } }, sum.summary_pt),
          sum.focus_pt ? h("p", { style: { marginTop: "8px" } }, h("b", "Para a próxima: "), sum.focus_pt) : null) : null);
    })) : h("p", { class: "empty" }, "Nenhuma conversa ainda.")));
  cols.append(h("section", { class: "section" }, h("h2", "Leituras em voz alta"),
    reading.runs.length ? h("ul", { class: "list", style: { marginTop: "14px" } }, reading.runs.map((r) =>
      h("li", { class: "row", style: { justifyContent: "space-between" } },
        h("span", `${shortDate(r.started_at)}: ${plural(r.recorded, "frase", "frases")}`),
        h("a", { class: "btn quiet", href: `#/leitura/rodada/${r.id}` }, "Ver o retrato")))) : h("p", { class: "empty" }, "Nenhuma leitura ainda.")));
}
