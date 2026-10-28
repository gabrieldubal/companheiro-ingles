// Hoje: o som da vez em destaque e a sessão do dia, curta, em passos.
import { api } from "../lib/api.js";
import { h, longDate, plural } from "../lib/dom.js";
import { get, set } from "../lib/store.js";
import * as tts from "../lib/tts.js";
import { ladderHref } from "./common.js";

const ROUTE = {
  "fale-certo": (s) => (s.mode === "escrever" ? "#/fale-certo/escrever" : "#/fale-certo"),
  treino: (s) => `#/treino/${s.tag}`,
  frases: () => "#/frases",
  escada: (s) => ladderHref(s.tag, s.word, s.heard_as, s.sentence),
  conversa: (s) => `#/conversar/${s.scenario}${s.mode === "escrever" ? "/escrever" : ""}`,
  leitura: () => "#/leitura",
  cartoes: () => "#/cartoes",
  ouvir: (s) => `#/ouvir/${s.tag}`,
  imitar: () => "#/imitar",
  usar: () => "#/usar",
  entender: (s) => `#/entender/${encodeURIComponent(s.key)}`,
};
const DAYS = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"];

// Onde você está agora. A sessão muda: com voz, o que só dá para fazer falando; sem voz, o resto.
function modeSwitch(silent) {
  const pick = (v) => () => { set("silent", v); window.dispatchEvent(new HashChangeEvent("hashchange")); };
  return h("div", { class: "mode-switch", role: "group", "aria-label": "Onde você está" },
    h("button", { type: "button", "aria-pressed": silent ? "false" : "true", onclick: pick(false) }, "Posso falar"),
    h("button", { type: "button", "aria-pressed": silent ? "true" : "false", onclick: pick(true) }, "Não posso falar"));
}

async function auto() {
  await api("/api/settings", { method: "PUT", body: { focus_tag: "" } });
  window.dispatchEvent(new HashChangeEvent("hashchange")); // redesenha Hoje
}

export async function render(root) {
  const silent = get("silent", false); // "não posso falar": guardado neste navegador
  const t = await api(`/api/today?silent=${silent}`);
  const minutes = t.steps.filter((s) => !s.done).reduce((a, s) => a + s.minutes, 0);
  const f = t.focus;

  // O símbolo do som responde ao toque: diz as palavras de exemplo, devagar.
  const left = f
    ? h("div", { class: "today-focus" },
        h("button", { class: `focus-glyph${f.symbol.length > 2 ? " wide" : ""}`, type: "button",
                      "aria-label": `Ouvir: ${f.example}`, title: `Ouvir: ${f.example}`,
                      onclick: () => { tts.unlock(); tts.speak(f.example.replace(/ × /g, ", "), 0.75); } }, f.symbol),
        h("div", { class: "focus-meta" },
          h("h2", `Som da vez: ${f.label}`),
          h("p", `Como em ${f.example} (toque no ${f.symbol} para ouvir). ` + (f.n
            ? `Você trocou em ${f.off} de ${f.n} vezes; nativos, em ${Math.round(100 * f.native)}%.` : "Ainda sem medidas suas desse som.")),
          f.chosen ? h("p", { class: "small" }, "Escolhido por você. ", h("button", { class: "btn quiet small", type: "button", onclick: auto },
            "Voltar ao automático")) : null,
          h("p", h("a", { href: `#/treino/${f.tag}` }, "Como fazer esse som"))))
    : h("div", { class: "today-focus" },
        h("p", { class: "focus-glyph", "aria-hidden": "true" }, "ə"),
        h("div", { class: "focus-meta" },
          h("h2", "Ainda sem som da vez"),
          h("p", t.pron_ready ? "Faça a leitura em voz alta: em 10 minutos o app descobre quais sons treinar."
                              : "O detector de pronúncia ainda está carregando ou desligado. Veja em Ajustes.")));

  // Só o próximo passo tem botão cheio: a tela diz o que fazer agora, e o resto espera.
  const nextIdx = t.steps.findIndex((s) => !s.done);
  const steps = h("ol", { class: "steps" }, t.steps.map((s, i) =>
    h("li", { class: s.done ? "done" : i === nextIdx ? "next" : "" },
      h("div", h("h3", s.title), h("p", s.detail), h("p", { class: "time" }, s.done ? "feito hoje" : `uns ${s.minutes} min`)),
      h("a", { class: `btn${i === nextIdx ? "" : " secondary"}`, href: ROUTE[s.kind](s) }, s.done ? "Repetir" : "Começar"))));

  const w = t.week;
  const week = h("div", { class: "week", role: "list" }, w.days.map((d, i) =>
    // "is-today", não "today": .today é a grade da tela inteira e bagunçava o dia de hoje
    h("div", { class: `day${d.minutes >= 5 ? " on" : d.minutes > 0 ? " some" : ""}${d.today ? " is-today" : ""}`, role: "listitem",
               title: d.minutes ? `${d.minutes} min` : "sem prática" },
      DAYS[i], h("div", { class: "dot" }))));

  const goal = t.goal
    ? h("p", { class: "soft" }, `Seu objetivo: ${t.goal}`)
    : h("p", { class: "soft" }, "Ainda sem objetivo. ", h("a", { href: "#/ajustes" }, "Escreva um em Ajustes"),
        ", e o tutor passa a puxar as conversas para ele.");

  // A sessão no meio; a semana, o objetivo e o que sobra ficam ao lado (no monitor) ou embaixo.
  const main = h("div", { class: "today-main" },
    h("p", { class: "date-line" }, longDate()),
    h("h1", "Sessão de hoje"),
    modeSwitch(silent),
    h("p", { class: "soft", style: { marginTop: "12px" } },
      (silent ? "Sem falar: o que dá para fazer em silêncio, com fone. " : "") +
      (minutes ? `Uns ${minutes} minutos, nesta ordem. Pode parar em qualquer passo.` : "Tudo feito por hoje. Se quiser, repita um passo.")),
    steps);

  const side = h("div", { class: "today-side" },
    t.later.length ? h("div", { class: "later side-block" }, h("h3", "Se sobrar tempo"),
      h("ul", t.later.map((s) => h("li", h("a", { href: ROUTE[s.kind](s) }, s.title), h("span", { class: "small muted" }, ` uns ${s.minutes} min`))))) : null,
    h("div", { class: "side-block" },
      h("h3", `${w.done} de ${plural(w.target, "sessão", "sessões")} nesta semana`),
      h("p", { class: "soft small", style: { marginTop: "4px" } },
        `Conta o dia com 5 minutos ou mais. ${w.minutes} min até agora.` +
        (w.streak_weeks ? ` ${plural(w.streak_weeks, "semana seguida", "semanas seguidas")} na meta.` : "")),
      week),
    h("div", { class: "side-block" }, goal),
    t.pron_pending ? h("p", { class: "small muted side-block" }, `Analisando a pronúncia de ${plural(t.pron_pending, "gravação", "gravações")} em segundo plano.`) : null);

  root.append(h("div", { class: "today" }, left, main, side));
}
