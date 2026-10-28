// Progresso: por sessão de estudo (o que cada sessão rendeu) ou por semana (a tendência),
// e a conversa, conversa a conversa.
import { api } from "../lib/api.js";
import { columns, line } from "../lib/charts.js";
import { clear, dayMonth, h, pct } from "../lib/dom.js";
import { get, set } from "../lib/store.js";

// A semana vai de segunda a domingo e leva o nome da segunda; "26/10" sozinho parecia um dia só.
function weekSpan(iso) {
  const start = new Date(`${iso}T12:00:00`);
  const end = new Date(start);
  end.setDate(start.getDate() + 6);
  return `${start.getDate()}/${start.getMonth() + 1} a ${end.getDate()}/${end.getMonth() + 1}`;
}

function weekLabel(iso) {
  const start = new Date(`${iso}T12:00:00`);
  const days = (Date.now() - start.getTime()) / 86400000;
  return days >= -0.5 && days < 6.5 ? "esta semana" : dayMonth(iso);
}

const WEEKDAY = ["domingo", "segunda", "terça", "quarta", "quinta", "sexta", "sábado"];
const hm = (d) => `${d.getHours()}h${String(d.getMinutes()).padStart(2, "0")}`;

function sessionWhen(s) {
  const a = new Date(s.start);
  const b = new Date(s.end);
  return `${WEEKDAY[a.getDay()]}, ${a.getDate()}/${a.getMonth() + 1}, ${hm(a)} a ${hm(b)}`;
}

// No eixo, a data; se houve mais de uma sessão no dia, a hora junto.
function sessionTick(s, all) {
  const a = new Date(s.start);
  const sameDay = all.filter((x) => x.start.slice(0, 10) === s.start.slice(0, 10)).length > 1;
  return sameDay ? `${a.getDate()}/${a.getMonth() + 1} ${a.getHours()}h` : `${a.getDate()}/${a.getMonth() + 1}`;
}

function stat(value, label) {
  return h("div", { class: "stat" }, h("div", { class: "v" }, value), h("div", { class: "l" }, label));
}

export async function render(root) {
  const p = await api("/api/progress");
  const settings = await api("/api/settings");
  const sessionMinutes = parseInt(settings.session_minutes || "15", 10);
  const native = Object.fromEntries(p.sounds.map((s) => [s.tag, s.native]));

  root.append(h("header", h("h1", "Progresso"),
    h("p", "Por sessão, o que cada estudo rendeu. Por semana, a tendência: melhora de pronúncia aparece em semanas. " +
           "Os dois comparam você com você mesmo.")),
    h("div", { class: "stats" },
      stat(String(p.totals.minutes), "minutos de prática"),
      stat(String(p.sessions.length), p.sessions.length === 1 ? "sessão de estudo" : "sessões de estudo"),
      stat(String(p.totals.conversations), p.totals.conversations === 1 ? "conversa" : "conversas"),
      stat(p.totals.checks.toLocaleString("pt-BR"), "sons checados")));

  let mode = get("progressMode", "sessao");
  const body = h("div");
  const pick = (m) => () => { mode = m; set("progressMode", m); draw(); };
  const switcher = h("div", { class: "mode-switch", role: "group", "aria-label": "Agrupar por" });
  function draw() {
    clear(switcher,
      h("button", { type: "button", "aria-pressed": String(mode === "sessao"), onclick: pick("sessao") }, "Por sessão"),
      h("button", { type: "button", "aria-pressed": String(mode === "semana"), onclick: pick("semana") }, "Por semana"));
    clear(body, mode === "sessao" ? sessionsView(p, sessionMinutes, native) : weeksView(p, settings));
  }
  root.append(switcher, body);
  draw();
  root.append(conversationSection(p));
}

// --- Por sessão -----------------------------------------------------------------------------

function sessionsView(p, sessionMinutes, native) {
  const all = p.sessions; // mais nova primeiro
  if (!all.length) {
    return h("div", { class: "empty section" }, h("p", "Ainda sem sessões. Uma sessão é um bloco de prática sem pausa maior que meia hora."),
      h("a", { class: "btn", href: "#/hoje" }, "Começar a de hoje"));
  }
  const recent = all.slice(0, 12).reverse(); // em ordem de tempo, para os gráficos
  const out = [];
  out.push(h("section", { class: "section" },
    h("div", { class: "chart-card" },
      h("h3", "Minutos por sessão"),
      h("p", { class: "sub" }, `As últimas ${recent.length === 1 ? "sessão" : `${recent.length} sessões`}. A linha é a duração que você escolheu em Ajustes.`),
      columns({
        data: recent.map((s) => ({ label: sessionTick(s, recent), value: s.minutes,
          tip: `${sessionWhen(s)}: ${s.kinds.map((k) => `${k.label} ${k.minutes} min`).join(", ")}` })),
        ref: { value: sessionMinutes, label: `sessão de ${sessionMinutes} min` }, unit: " min",
      }))));

  // Um gráfico por som (uma série cada), só com as sessões que mediram o som pelo menos 3 vezes.
  const totals = {};
  recent.forEach((s) => s.pron.sounds.forEach((x) => {
    totals[x.tag] = totals[x.tag] || { ...x, n: 0, sessions: 0 };
    totals[x.tag].n += x.n;
    if (x.n >= 3) totals[x.tag].sessions += 1;
  }));
  const tags = Object.values(totals).filter((t) => t.n >= 5 && native[t.tag] != null).slice(0, 6);
  if (tags.length) {
    out.push(h("section", { class: "section" }, h("h2", "Pronúncia por som, sessão a sessão"),
      h("p", "Quanto o som saiu diferente do esperado em cada sessão (só as que mediram o som 3 vezes ou mais). A linha reta é a taxa dos nativos."),
      h("div", { class: "charts" }, tags.map((t) => {
        const pts = recent.map((s) => ({ s, x: s.pron.sounds.find((y) => y.tag === t.tag) })).filter(({ x }) => x && x.n >= 3);
        return h("div", { class: "chart-card" },
          h("h3", h("span", { class: "ipa", style: { fontSize: "1.4rem", marginRight: "8px" } }, t.symbol), t.label),
          h("p", { class: "sub" }, pts.length > 1 ? `${pts.length} sessões` : "Uma sessão só por enquanto"),
          line({
            points: pts.map(({ s, x }) => ({ label: sessionTick(s, recent), value: x.off / x.n,
              tip: `${x.n - x.off} de ${x.n} certos, ${sessionWhen(s)}` })),
            ref: { value: native[t.tag], label: `nativos ${pct(native[t.tag])}` }, format: pct, color: "bad", max: 1,
          }));
      }))));
  }

  out.push(h("section", { class: "section" }, h("h2", "As sessões"),
    h("p", "A mais nova em cima. Ao lado de cada som, a sessão anterior que mediu esse som."),
    h("ul", { class: "grid-list session-list", style: { "--col": "480px" } }, all.slice(0, 20).map((s, i) => sessionItem(s, all.slice(i + 1))))));
  return out;
}

function sessionItem(s, older) {
  const lines = [];
  if (s.pron.n) {
    lines.push(h("p", `Sons que você treina: ${s.pron.n - s.pron.off} de ${s.pron.n} certos (${pct((s.pron.n - s.pron.off) / s.pron.n)}).`));
    lines.push(h("ul", { class: "sound-chips" }, s.pron.sounds.filter((x) => x.n >= 3).map((x) => {
      const before = older.map((o) => o.pron.sounds.find((y) => y.tag === x.tag)).find((y) => y && y.n >= 3);
      const now = (x.n - x.off) / x.n;
      const was = before ? (before.n - before.off) / before.n : null;
      const trend = was == null ? "" : now > was + 0.05 ? "melhor" : now < was - 0.05 ? "pior" : "igual";
      return h("li", { class: trend ? `t-${trend}` : "" },
        h("b", { class: "ipa" }, x.symbol), ` ${x.n - x.off} de ${x.n}`,
        was != null ? h("span", { class: "small muted" }, ` (antes ${pct(was)})`) : null);
    })));
  }
  if (s.practice.n) lines.push(h("p", `Fale certo: ${s.practice.ok} de ${s.practice.n}.`));
  if (s.cards.n) lines.push(h("p", `Cartões: lembrou ${s.cards.ok} de ${s.cards.n}.`));
  if (s.listen.n) lines.push(h("p", `Ouvido: acertou ${s.listen.ok} de ${s.listen.n} palavras.`));
  (s.lessons || []).forEach((l) => lines.push(h("p", `Entender: ${l.title} (exercício ${l.score} de ${l.total}).`)));
  s.conversations.forEach((c) => lines.push(h("p", `Conversa (${c.title}): ${c.words.toLocaleString("pt-BR")} palavras` +
    (c.errors_per_100 != null ? `, ${String(c.errors_per_100).replace(".", ",")} erros a cada 100.` : "."))));
  return h("li",
    h("div", { class: "row", style: { justifyContent: "space-between", alignItems: "baseline" } },
      h("h3", sessionWhen(s)), h("span", { class: "small muted" }, `${s.minutes} min`)),
    h("p", { class: "small soft" }, s.kinds.map((k) => `${k.label} ${k.minutes} min`).join(", ")),
    lines.length ? h("div", { class: "session-results" }, lines) : h("p", { class: "small muted" }, "Sem resultados medidos nesta sessão."));
}

// --- Por semana -----------------------------------------------------------------------------

function weeksView(p, settings) {
  const goalMinutes = p.target * parseInt(settings.session_minutes || "15", 10);
  const out = [h("section", { class: "section" },
    h("div", { class: "chart-card" },
      h("h3", "Minutos de prática por semana"),
      h("p", { class: "sub" }, `As últimas 8 semanas, de segunda a domingo; cada barra leva a data da segunda. A linha é a sua meta: ${p.target} sessões de ${settings.session_minutes} minutos.`),
      columns({
        data: p.weeks.map((w) => ({ label: weekLabel(w.week), value: w.minutes,
                                    tip: `${weekSpan(w.week)}: ${w.days} ${w.days === 1 ? "dia" : "dias"} com prática` })),
        ref: { value: goalMinutes, label: `meta ${goalMinutes} min` }, unit: " min",
      })))];

  const sounds = h("section", { class: "section" }, h("h2", "Pronúncia por som"),
    h("p", "Quanto cada som saiu diferente do esperado, semana a semana. A linha reta é a taxa dos nativos: é o chão."));
  if (p.sounds.length) {
    sounds.append(h("div", { class: "charts" }, p.sounds.map((s) => h("div", { class: "chart-card" },
      h("h3", h("span", { class: "ipa", style: { fontSize: "1.4rem", marginRight: "8px" } }, s.symbol), s.label),
      h("p", { class: "sub" }, s.points.length > 1 ? `${s.n} checagens` : `${s.n} checagens, uma semana só por enquanto`),
      line({
        points: s.points.map((pt) => ({ label: weekLabel(pt.week), value: pt.rate, tip: `${pt.off} de ${pt.n} de ${weekSpan(pt.week)}` })),
        ref: { value: s.native, label: `nativos ${pct(s.native)}` }, format: pct, color: "bad", max: 1,
      })))));
  } else {
    sounds.append(h("div", { class: "empty" }, h("p", "Ainda sem medidas. A leitura em voz alta dá o primeiro ponto de cada som."),
      h("a", { class: "btn", href: "#/leitura" }, "Fazer a leitura")));
  }
  out.push(sounds);
  return out;
}

// --- Conversa (igual nos dois modos: já é conversa a conversa) ----------------------------------

function conversationSection(p) {
  const convo = h("section", { class: "section" }, h("h2", "Conversa"),
    h("p", "Erros por 100 palavras (menos é melhor) e o tamanho das suas respostas, conversa a conversa."));
  if (p.conversations.length) {
    const pts = p.conversations.map((c, i) => ({ label: `#${i + 1}`, c }));
    convo.append(h("div", { class: "charts" },
      h("div", { class: "chart-card" }, h("h3", "Erros por 100 palavras"),
        h("p", { class: "sub" }, p.conversations.some((c) => c.partial) ? "A primeira conversa só contou os cartões: o número dela está baixo." : "Contados pelo tutor em cada resposta."),
        line({ points: pts.map(({ label, c }) => ({ label, value: c.errors_per_100 || 0,
          tip: `${c.errors} erros em ${c.words} palavras${c.partial ? " (contagem parcial)" : ""}` })), color: "bad" })),
      h("div", { class: "chart-card" }, h("h3", "Palavras por resposta"),
        h("p", { class: "sub" }, "Respostas longas sem travar são fluência. Curtas e fechadas são clareza."),
        line({ points: pts.map(({ label, c }) => ({ label, value: c.words_per_answer || 0, tip: `${c.answers} respostas, ${c.words} palavras` })),
          color: "good" }))));
    const levels = p.conversations.filter((c) => c.cefr);
    if (levels.length) {
      convo.append(h("ul", { class: "list section" }, levels.map((c) => h("li", { class: "row", style: { justifyContent: "space-between" } },
        h("span", `${dayMonth(c.date)}: nível estimado ${c.cefr}${c.scale ? ` (≈ ${c.scale} na sua escala)` : ""}`),
        h("span", { class: "small muted" }, `${c.words} palavras`)))));
    }
  } else {
    convo.append(h("div", { class: "empty" }, h("p", "Ainda sem conversas."), h("a", { class: "btn", href: "#/conversar" }, "Conversar")));
  }
  return convo;
}
