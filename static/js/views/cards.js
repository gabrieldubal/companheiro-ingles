// Cartões: revisão com repetição espaçada (Errei, Difícil, Bom, Fácil) e a lista para editar.
// Dois jeitos de responder: escrevendo (o app confere e sugere a nota) ou de cabeça.
// Teclado: Enter confere a resposta escrita (vazia, vira o cartão), espaço vira (de cabeça),
// 1 a 4 dão a nota, Z desfaz a última nota, O toca o verso.
import { track } from "../lib/activity.js";
import { api } from "../lib/api.js";
import { clear, collapseRepeats, h, pct, plural, shortDate, toast } from "../lib/dom.js";
import { get, set } from "../lib/store.js";
import * as tts from "../lib/tts.js";

const RATINGS = [
  [1, "Errei", "Não lembrou, ou lembrou errado"],
  [2, "Difícil", "Lembrou com muito esforço"],
  [3, "Bom", "Lembrou"],
  [4, "Fácil", "Lembrou na hora"],
];
const KIND = { frase: "Correção sua", palavra: "Palavra nova", livre: "Cartão" };
const SOURCE = { caderno: "das suas conversas", palavra: "sugerida numa conversa", perguntar: "criado no Perguntar",
                 voce: "criado por você" };

export function when(o) {
  if (!o) return "";
  if (o.minutes != null) return o.minutes < 60 ? `${o.minutes} min` : `${Math.round(o.minutes / 60)} h`;
  const d = o.days;
  if (d < 30) return plural(d, "dia", "dias");
  if (d < 365) { const m = Math.round(d / 30); return plural(m, "mês", "meses"); }
  return "1 ano";
}

function stateText(c) {
  if (c.suspended) return "suspenso";
  if (c.state === "new") return "novo";
  if (c.state !== "review") return "aprendendo";
  const days = Math.round((new Date(c.due) - Date.now()) / 86400000);
  return days <= 0 ? "para hoje" : `volta em ${plural(days, "dia", "dias")}`;
}

/** A frente: o que você tem que lembrar. */
function frontOf(c, { hintOpen = false } = {}) {
  const box = h("div", { class: "card-front" });
  if (c.kind === "frase" && c.meaning) {
    // O que você queria dizer é a pergunta; o que você disse fica embaixo, menor, como pista.
    box.append(h("p", { class: "ask" }, "Como se diz, do jeito certo:"), h("p", { class: "card-text" }, c.meaning),
      h("p", { class: "ask" }, "Você tinha dito:"), h("p", { class: "said-small" }, collapseRepeats(c.front)));
  } else if (c.kind === "frase") {
    box.append(h("p", { class: "ask" }, "Diga do jeito certo, em voz alta ou de cabeça:"),
      h("p", { class: "card-text wrong" }, collapseRepeats(c.front)));
  }
  if (c.kind === "frase") {
    if (c.hint) {
      const hint = h("p", { class: "small soft", hidden: !hintOpen }, `Tema: ${c.hint}`);
      const btn = h("button", { class: "btn quiet small", type: "button", hidden: hintOpen,
                                onclick: () => { hint.hidden = false; btn.hidden = true; } }, "Ver o tema do erro");
      box.append(btn, hint);
    }
  } else if (c.kind === "palavra") {
    box.append(h("p", { class: "ask" }, "Como se diz em inglês:"), h("p", { class: "card-text" }, c.front),
      c.hint ? h("p", { class: "cloze" }, c.hint) : null);
  } else {
    box.append(h("p", { class: "card-text" }, c.front));
  }
  return box;
}

// O que a conferência disse da resposta escrita.
const VERDICT = {
  certo: ["Certo.", "var(--mata)"],
  quase: ["Quase. Confira as palavras marcadas.", "var(--ink)"],
  errado: ["Não bateu.", "var(--pitaya)"],
};

function checkBlock(r) {
  let [title, color] = VERDICT[r.verdict];
  if (r.verdict === "certo" && !r.exact) title = "Certo, com uma diferença pequena.";
  if (r.verdict === "errado" && r.kept.length) title = "Não bateu: o erro continua na sua frase.";
  const mark = r.verdict !== "certo";
  return h("div", { class: "card-check" },
    h("p", { class: "ask" }, "Você escreveu:"),
    h("p", { class: "typed-line" }, r.yours.map((x, i) => [i ? " " : "", mark && !x.ok ? h("span", { class: "tok-off" }, x.w) : x.w])),
    h("p", { style: { color, fontWeight: 700, marginTop: "4px" } }, title));
}

/** O verso. Com resposta escrita que não bateu, as palavras que faltaram ficam sublinhadas. */
function backOf(c, checked = null) {
  const marks = checked && checked.verdict !== "certo" ? checked.answer : null;
  return h("div", { class: "card-back" },
    h("p", { class: "card-text answer" }, marks
      ? marks.map((x, i) => [i ? " " : "", x.ok ? x.w : h("span", { class: "missed" }, x.w)]) : c.back),
    c.note ? h("p", { class: c.kind === "palavra" ? "cloze" : "soft" }, c.note) : null,
    c.speak ? h("p", h("button", { class: "play", type: "button", onclick: () => tts.speak(c.speak, 0.85) }, "▶ Ouvir (O)")) : null);
}

export async function render(root, [mode], alive) {
  if (mode === "todos") return renderList(root, alive);
  const data = await api("/api/deck/session");
  if (!alive()) return;
  const tracker = track("cartoes");
  const queue = data.cards;
  let total = queue.length;
  let done = 0;
  const seen = new Set(); // cartões diferentes revisados (um cartão errado volta e conta uma vez só)
  let current = null;
  let flipped = false;
  let busy = false;
  let lastRated = false;
  let typing = get("cardsType", true); // escrever a resposta antes de virar
  let checked = null; // a conferência da resposta escrita do cartão da vez
  const stage = h("section", { class: "review stage" });
  const counter = h("p", { class: "muted small" });
  const bar = h("div", { class: "progressbar" }, h("span"));
  // Ao lado: o baralho em números e o teclado (a revisão inteira dá para fazer sem o mouse).
  const deckBox = h("div", { class: "side-block" });
  const modeBox = h("div", { class: "side-block" });
  const keysBox = h("div", { class: "side-block" });
  root.append(h("header", { class: "row", style: { justifyContent: "space-between", alignItems: "flex-end" } },
    h("div", h("h1", "Cartões"), h("p", "As suas correções e palavras, na hora certa de lembrar. Diga a resposta antes de virar.")),
    h("a", { class: "btn secondary small", href: "#/cartoes/todos" }, "Todos os cartões")),
    h("div", { class: "bench" }, h("div", { class: "bench-main" }, counter, bar, stage),
      h("aside", { class: "bench-side lead" }, modeBox, deckBox, keysBox)));

  // Escrevendo ou de cabeça: fica guardado neste navegador.
  function drawMode() {
    const pick = (v) => () => {
      typing = v;
      set("cardsType", v);
      drawMode();
      if (current && !flipped) show();
    };
    clear(modeBox, h("h3", "Como responder"),
      h("div", { class: "mode-switch", role: "group", "aria-label": "Como responder", style: { marginTop: "4px" } },
        h("button", { type: "button", "aria-pressed": String(typing), onclick: pick(true) }, "Escrevendo"),
        h("button", { type: "button", "aria-pressed": String(!typing), onclick: pick(false) }, "De cabeça")),
      h("p", { class: "small soft", style: { marginTop: "8px" } }, typing
        ? "Você escreve, o app confere e sugere a nota. A nota final é sua."
        : "Diga a resposta de cabeça, vire e dê a nota."));
    clear(keysBox, h("h3", "Teclado"), h("ul", { class: "keys" },
      typing ? h("li", h("kbd", "Enter"), "confere (vazia, vira o cartão)") : h("li", h("kbd", "espaço"), "vira o cartão"),
      typing ? h("li", h("kbd", "Enter"), "de novo aceita a nota sugerida") : null,
      h("li", h("kbd", "1"), "a ", h("kbd", "4"), "dão a nota"),
      h("li", h("kbd", "Z"), "desfaz a última nota"),
      h("li", h("kbd", "O"), "toca o verso")));
  }
  drawMode();

  function progress() {
    counter.textContent = queue.length ? `Faltam ${queue.length}. Novos hoje: até ${data.summary.per_day}.` : "";
    bar.firstChild.style.width = `${total ? (100 * done) / total : 100}%`;
    const s = data.summary;
    const c = s.counts || {};
    clear(deckBox, h("h3", "Hoje"),
      h("p", { class: "tally" }, `${seen.size} ${seen.size === 1 ? "revisado" : "revisados"}`),
      h("p", { class: "small soft" }, queue.length ? `Faltam ${queue.length} nesta sessão.` : "Nada mais para hoje."),
      c.total ? h("p", { class: "small soft", style: { marginTop: "10px" } },
        `No baralho: ${plural(c.total, "cartão", "cartões")}, ${c.new} ${c.new === 1 ? "novo" : "novos"}, ${c.learning} aprendendo, ${c.review} em revisão.`) : null,
      s.retention != null && s.retention_n >= 10 ? h("p", { class: "small soft" }, `Nos últimos 30 dias você lembrou ${pct(s.retention)} das revisões.`) : null,
      s.tomorrow ? h("p", { class: "small muted" }, `Amanhã ${s.tomorrow === 1 ? "volta 1 cartão" : `voltam ${s.tomorrow} cartões`}.`) : null);
  }

  function show() {
    progress();
    if (!queue.length) { finish(); return; }
    current = queue[0];
    flipped = false;
    checked = null;
    const k = KIND[current.kind] + (SOURCE[current.source] ? `, ${SOURCE[current.source]}` : "");
    const answer = typing ? typedAnswer() : null;
    clear(stage,
      h("p", { class: "small muted" }, current.state === "new" ? `${k}. Novo.` : k),
      frontOf(current),
      answer ? answer.el : h("div", { class: "row", style: { marginTop: "26px" } },
        h("button", { class: "btn", type: "button", onclick: flip }, "Virar (espaço)")),
      undoLink());
    if (answer) setTimeout(() => answer.box.focus(), 0);
  }

  // A caixa da resposta: Enter confere; com a caixa vazia, Enter vira o cartão (quando não lembrou).
  function typedAnswer() {
    const card = current;
    const box = h("textarea", { rows: 2, "aria-label": "Sua resposta",
      placeholder: card.kind === "palavra" ? "Escreva a palavra em inglês" : "Escreva a resposta em inglês" });
    const go = h("button", { class: "btn", type: "button" }, "Conferir");
    const run = async () => {
      if (go.disabled || current !== card || flipped) return;
      const text = box.value.trim();
      if (!text) { flip(); return; }
      go.disabled = true;
      try {
        const r = await api(`/api/deck/cards/${card.id}/check`, { body: { text } });
        if (!alive() || current !== card || flipped) return;
        checked = r;
        flip();
      } catch (e) {
        toast(e.message);
        go.disabled = false;
      }
    };
    go.onclick = run;
    box.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); run(); } });
    return { box, el: h("div", { style: { marginTop: "22px" } },
      h("div", { class: "typed-answer", style: { marginTop: 0 } }, box, go),
      h("div", { class: "row", style: { marginTop: "8px" } },
        h("button", { class: "btn quiet small", type: "button", onclick: flip }, "Não lembrei: virar"),
        h("span", { class: "small muted" }, "Enter confere."))) };
  }

  function undoLink() {
    return lastRated ? h("p", { style: { marginTop: "22px" } },
      h("button", { class: "btn quiet small", type: "button", onclick: undo }, "Desfazer a última nota (Z)")) : null;
  }

  function flip() {
    if (!current || flipped) return;
    flipped = true;
    tts.unlock();
    const k = KIND[current.kind] + (SOURCE[current.source] ? `, ${SOURCE[current.source]}` : "");
    const sug = checked?.suggest;
    const ratings = h("div", { class: "ratings", role: "group", "aria-label": "Como foi" }, RATINGS.map(([g, label, title]) =>
      h("button", { class: `rate-btn r${g}${g === sug ? " suggested" : ""}`, type: "button", title, onclick: () => rate(g) },
        h("span", { class: "k" }, g === sug ? `${g}, sugerida` : `${g}`), h("b", label), h("span", { class: "t" }, when(current.options[g])))));
    clear(stage,
      h("p", { class: "small muted" }, k),
      frontOf(current, { hintOpen: true }),
      checked ? checkBlock(checked) : null,
      backOf(current, checked),
      ratings,
      sug ? h("p", { class: "small muted", style: { marginTop: "8px" } },
        `Pela sua resposta, a sugestão é ${RATINGS[sug - 1][1]}. Enter aceita; se custou mais ou menos do que isso, escolha outra.`) : null,
      undoLink()); // sem falar sozinho: dá para revisar em silêncio, no trabalho
    // Com a sugestão em foco, Enter (ou espaço) aceita: escrever, Enter, Enter.
    if (sug) ratings.querySelector(".suggested")?.focus({ preventScroll: true });
  }

  async function rate(g) {
    if (busy || !flipped) return;
    busy = true;
    tracker.bump();
    try {
      const r = await api(`/api/deck/cards/${current.id}/answer`, { body: { rating: g } });
      if (!alive()) return;
      data.summary = r.summary;
      seen.add(current.id);
      queue.shift();
      lastRated = true;
      if (r.again) {
        // Volta ainda nesta sessão: uns cartões depois, ou no fim se a fila for curta.
        queue.splice(Math.min(queue.length, 3), 0, r.card);
        total += 1;
      }
      done += 1;
      show();
    } catch (e) {
      toast(e.message);
    } finally {
      busy = false;
    }
  }

  async function undo() {
    if (busy) return;
    busy = true;
    try {
      const r = await api("/api/deck/undo", { body: {} });
      if (!alive()) return;
      // O cartão desfeito volta para a frente da fila (e sai do lugar onde tinha voltado, se for o caso).
      const i = queue.findIndex((c) => c.id === r.card.id);
      if (i >= 0) { queue.splice(i, 1); total -= 1; }
      queue.unshift(r.card);
      done = Math.max(done - 1, 0);
      lastRated = false;
      show();
    } catch (e) {
      toast(e.message);
    } finally {
      busy = false;
    }
  }

  // Acabou a fila do dia, mas há novos esperando: dá para puxar mais 10 agora, além do limite.
  async function more(btn) {
    btn.disabled = true;
    btn.textContent = "Puxando…";
    try {
      const r = await api("/api/deck/session?mais=10");
      if (!alive()) return;
      const ids = new Set(queue.map((c) => c.id));
      const fresh = r.cards.filter((c) => c.state === "new" && !ids.has(c.id) && !seen.has(c.id));
      if (!fresh.length) { toast("Não sobrou cartão novo para puxar."); return; }
      data.summary = r.summary;
      queue.push(...fresh);
      total += fresh.length;
      show();
    } catch (e) {
      toast(e.message);
      btn.disabled = false;
      btn.textContent = "Mais 10 novos agora";
    }
  }

  function finish() {
    current = null;
    const s = data.summary;
    const waiting = s.counts.new; // novos que ainda não apareceram nenhuma vez
    clear(stage,
      h("h2", done ? "Feito por hoje" : (s.counts.total ? "Nada para revisar agora" : "O baralho ainda está vazio")),
      h("p", { class: "soft", style: { marginTop: "8px" } }, s.counts.total
        ? `${seen.size ? `Você revisou ${plural(seen.size, "cartão", "cartões")}. ` : ""}` +
          (s.tomorrow ? `Amanhã ${s.tomorrow === 1 ? "volta 1 cartão" : `voltam ${s.tomorrow} cartões`}.` : "Amanhã não há revisões marcadas.") +
          (s.retention != null && s.retention_n >= 10 ? ` Nos últimos 30 dias você lembrou ${pct(s.retention)} das revisões.` : "")
        : "Os cartões nascem sozinhos das correções das conversas e das palavras novas. Converse uma vez, ou crie um cartão."),
      waiting ? h("div", { class: "tip", style: { marginTop: "18px" } },
        h("p", h("b", `${plural(waiting, "cartão novo esperando", "cartões novos esperando")}. `),
          `O limite de hoje (${s.per_day} novos) já foi. Dá para puxar mais agora, ou mudar o limite por dia em Ajustes. ` +
          "Cada novo volta umas 5 vezes nas semanas seguintes: 10 novos por dia viram uns 40 a 60 por dia depois de um mês."),
        h("div", { class: "row", style: { marginTop: "10px" } },
          h("button", { class: "btn", type: "button", onclick: (e) => more(e.currentTarget) }, "Mais 10 novos agora"),
          h("a", { class: "btn secondary small", href: "#/ajustes" }, "Mudar o limite por dia"))) : null,
      h("div", { class: "row section", style: { marginTop: "22px" } },
        h("a", { class: waiting ? "btn secondary" : "btn", href: "#/hoje" }, "Voltar para hoje"),
        h("a", { class: "btn secondary", href: "#/cartoes/todos" }, s.counts.total ? "Ver todos os cartões" : "Criar um cartão")),
      undoLink());
  }

  const onKey = (e) => {
    if (["TEXTAREA", "INPUT", "SELECT"].includes(document.activeElement.tagName) || e.ctrlKey || e.metaKey || e.altKey) return;
    if (e.code === "Space" || e.key === "Enter") {
      if (current && !flipped) { e.preventDefault(); flip(); }
    } else if (/^[1-4]$/.test(e.key) && flipped) {
      rate(Number(e.key));
    } else if (e.key.toLowerCase() === "z" && lastRated) {
      undo();
    } else if (e.key.toLowerCase() === "o" && current?.speak && flipped) {
      tts.speak(current.speak, 0.85);
    }
  };
  document.addEventListener("keydown", onKey);
  show();
  return () => { document.removeEventListener("keydown", onKey); tracker.stop(); };
}

// --- Todos os cartões: procurar, criar, editar, suspender, apagar --------------------------

async function renderList(root, alive) {
  let filter = { q: "", kind: "" };
  const list = h("ul", { class: "list" });
  const totals = h("p", { class: "soft" });
  const search = h("input", { type: "search", placeholder: "Procurar nos cartões", "aria-label": "Procurar nos cartões" });
  const kinds = h("div", { class: "tabs", role: "tablist" });

  const form = newForm();
  root.append(h("header",
    h("p", { class: "date-line" }, h("a", { href: "#/cartoes" }, "Cartões"), " / todos"),
    h("h1", "Todos os cartões")),
    h("div", { class: "bench" },
      h("div", { class: "bench-main" }, h("div", { class: "row", style: { margin: "0 0 10px" } },
        h("label", { class: "field", style: { margin: 0, flex: "1" } }, search)), kinds, list),
      h("aside", { class: "bench-side lead" }, h("div", { class: "side-block" }, totals), h("div", { class: "side-block" }, form))));
  form.open = matchMedia("(min-width: 1280px)").matches;

  function drawKinds(byKind) {
    clear(kinds, [["", "Todos"], ["frase", "Correções"], ["palavra", "Palavras"], ["livre", "Criados"]].map(([k, label]) =>
      h("button", { type: "button", role: "tab", "aria-selected": filter.kind === k ? "true" : "false",
                    onclick: () => { filter.kind = k; load(); } }, k ? `${label} (${byKind[k] || 0})` : label)));
  }

  async function load() {
    const d = await api(`/api/deck?q=${encodeURIComponent(filter.q)}&kind=${filter.kind}`);
    if (!alive()) return;
    const c = d.summary.counts;
    totals.textContent = c.total
      ? `${plural(c.total, "cartão", "cartões")}: ${c.new} ${c.new === 1 ? "novo" : "novos"}, ${c.learning} aprendendo, ` +
        `${c.review} em revisão${c.suspended ? `, ${c.suspended} suspensos` : ""}. ` +
        `Até ${d.summary.per_day} novos por dia (muda em Ajustes).`
      : "Ainda sem cartões.";
    drawKinds(c.by_kind);
    clear(list, d.cards.length ? d.cards.map(row) : h("li", { class: "soft" }, filter.q ? "Nenhum cartão com esse texto." : "Nenhum cartão aqui ainda."));
  }

  function row(c) {
    const li = h("li", { class: "card-row" });
    const view = () => clear(li,
      h("div",
        h("p", h("span", { class: c.kind === "frase" ? "card-front-line wrong" : "card-front-line" }, c.front), "  →  ",
          h("b", { class: "serif" }, c.back)),
        h("p", { class: "small muted" }, `${KIND[c.kind]}, ${stateText(c)}` + (c.reps ? `, ${plural(c.reps, "revisão", "revisões")}` : "") +
          (c.lapses ? `, esqueceu ${plural(c.lapses, "vez", "vezes")}` : "") + `. Criado em ${shortDate(c.created_at)}.`)),
      h("div", { class: "row" },
        h("button", { class: "play", type: "button", onclick: edit }, "Editar"),
        h("button", { class: "play", type: "button", onclick: () => save({ suspended: !c.suspended }) }, c.suspended ? "Reativar" : "Suspender"),
        h("button", { class: "play", type: "button", onclick: remove }, "Apagar")));
    async function save(body) {
      try {
        Object.assign(c, await api(`/api/deck/cards/${c.id}`, { method: "PUT", body }));
        view();
      } catch (e) { toast(e.message); }
    }
    async function remove() {
      if (!confirm(`Apagar o cartão "${c.front}"?`)) return;
      try {
        await api(`/api/deck/cards/${c.id}`, { method: "DELETE" });
        li.remove();
      } catch (e) { toast(e.message); }
    }
    function edit() {
      const f = h("input", { type: "text", value: c.front });
      const b = h("input", { type: "text", value: c.back });
      const n = h("input", { type: "text", value: c.note });
      clear(li,
        h("label", { class: "field" }, h("span", "Frente"), f),
        h("label", { class: "field" }, h("span", "Verso"), b),
        h("label", { class: "field" }, h("span", c.kind === "palavra" ? "Exemplo" : "Nota"), n),
        h("div", { class: "row" },
          h("button", { class: "btn small", type: "button", onclick: () => save({ front: f.value, back: b.value, note: n.value }) }, "Salvar"),
          h("button", { class: "btn quiet small", type: "button", onclick: view }, "Cancelar")));
      f.focus();
    }
    view();
    return li;
  }

  function newForm() {
    const f = h("input", { type: "text", placeholder: "Ex.: Como se diz: prazo final" });
    const b = h("input", { type: "text", placeholder: "Ex.: deadline" });
    const n = h("input", { type: "text", placeholder: "Opcional: um exemplo ou o porquê" });
    const btn = h("button", { class: "btn small", type: "button" }, "Criar cartão");
    btn.onclick = async () => {
      btn.disabled = true;
      try {
        await api("/api/deck/cards", { body: { front: f.value, back: b.value, note: n.value } });
        f.value = b.value = n.value = "";
        toast("Cartão criado. Ele entra na revisão como novo.");
        load();
      } catch (e) {
        toast(e.message);
      } finally {
        btn.disabled = false;
      }
    };
    return h("details", { class: "new-card" }, h("summary", "Criar um cartão"),
      h("div", { style: { marginTop: "14px" } },
        h("label", { class: "field" }, h("span", "Frente: o que você vê"), f),
        h("label", { class: "field" }, h("span", "Verso: a resposta"), b),
        h("label", { class: "field" }, h("span", "Nota"), n), btn));
  }

  let timer;
  search.oninput = () => { clearTimeout(timer); timer = setTimeout(() => { filter.q = search.value; load(); }, 250); };
  await load();
}
