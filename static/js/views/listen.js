// Ouvir a diferença: uma palavra de um par mínimo, numa voz sorteada; você escolhe qual ouviu.
// Teclado: 1 e 2 (ou ← e →) escolhem, R repete, espaço segue.
import { track } from "../lib/activity.js";
import { api } from "../lib/api.js";
import { clear, h, pct, plural, toast } from "../lib/dom.js";
import * as tts from "../lib/tts.js";

const ROUND = 20;

export async function render(root, [which], alive) {
  const d = await api("/api/listen");
  if (!alive()) return;
  if (!which) return renderHub(root, d);
  const tags = which === "misturado" ? d.mix : [which];
  const sets = d.sounds.filter((s) => tags.includes(s.tag));
  if (!sets.length) { location.hash = "#/ouvir"; return; }
  return renderRound(root, sets, which === "misturado", alive);
}

// O Chrome carrega as vozes depois da página: a linha se refaz quando elas chegam.
function voicesNote() {
  const p = h("p", { class: "small" });
  const draw = () => {
    const n = tts.listVoices().length;
    p.className = n >= 3 ? "small muted" : "small soft";
    p.textContent = n >= 3 ? `Este navegador tem ${n} vozes em inglês: cada palavra sai numa delas.`
      : n ? `Este navegador só tem ${plural(n, "voz", "vozes")} em inglês, e o treino rende mais com várias. No Microsoft Edge há dezenas de vozes naturais.`
      : "Este navegador ainda não mostrou vozes em inglês. Se continuar assim, abra o app no Edge ou no Chrome.";
  };
  draw();
  if ("speechSynthesis" in window) {
    const onChange = () => {
      if (!p.isConnected) { speechSynthesis.removeEventListener("voiceschanged", onChange); return; } // saiu da tela
      setTimeout(draw, 0);
    };
    speechSynthesis.addEventListener("voiceschanged", onChange);
  }
  return p;
}

function renderHub(root, d) {
  const names = d.mix.map((t) => d.sounds.find((s) => s.tag === t)?.symbol).filter(Boolean);
  root.append(h("header",
    h("p", { class: "date-line" }, h("a", { href: "#/pronuncia" }, "Pronúncia"), " / ouvir"),
    h("h1", "Ouvir a diferença"),
    h("p", "Você ouve uma palavra, numa voz diferente a cada vez, e escolhe qual foi: ship ou sheep, think ou sink. " +
           "Treinar o ouvido com várias vozes ajuda a boca, porque é difícil produzir uma diferença que você ainda não escuta."),
    voicesNote()),
    h("div", { class: "row", style: { marginBottom: "30px" } },
      h("a", { class: "btn", href: "#/ouvir/misturado" }, `Misturado: ${names.join(", ")}`),
      h("span", { class: "soft small" }, `${ROUND} palavras com os seus sons fracos.`)),
    h("ul", { class: "sound-list" }, d.sounds.map((s) => h("li", { class: "sound-row listen-row" },
      h("span", { class: "sym", "aria-hidden": "true" }, s.symbol),
      h("div", h("h3", s.label), h("p", { class: "ex" }, s.pairs.slice(0, 3).map((p) => p.join(" ou ")).join(", "))),
      h("span", { class: "count" }, s.n ? `${s.ok} de ${s.n} (${pct(s.ok / s.n)})` : "ainda não treinado"),
      h("span", { class: "act" }, h("a", { class: "btn small secondary", href: `#/ouvir/${s.tag}` }, "Treinar")),
      s.misses.length ? h("p", { class: "more small muted" }, "Mais confundidas: " +
        s.misses.map((m) => `ouviu ${m.heard} e marcou ${m.chose} (${m.n}x)`).join("; ")) : null))));
}

function renderRound(root, sets, mixed, alive) {
  const tracker = track("ouvir", mixed ? "misturado" : sets[0].tag);
  const stage = h("section", { class: "stage" });
  const title = mixed ? "misturado" : sets[0].label;
  // Ao lado: o placar da rodada, palavra a palavra, e o teclado.
  const tally = h("div", { class: "side-block" });
  root.append(h("header",
    h("p", { class: "date-line" }, h("a", { href: "#/ouvir" }, "Ouvir a diferença"), ` / ${title}`),
    h("h1", mixed ? "Ouvir a diferença: misturado" : `Ouvir a diferença: ${sets[0].label}`),
    voicesNote()),
    h("div", { class: "bench section", style: { marginTop: "20px" } }, h("div", { class: "bench-main" }, stage),
      h("aside", { class: "bench-side" }, tally,
        h("div", { class: "side-block" }, h("h3", "Teclado"), h("ul", { class: "keys" },
          h("li", h("kbd", "1"), "ou ", h("kbd", "←"), "a primeira palavra"),
          h("li", h("kbd", "2"), "ou ", h("kbd", "→"), "a segunda"),
          h("li", h("kbd", "R"), "ouvir de novo"),
          h("li", h("kbd", "espaço"), "a próxima, depois de responder"))))));

  function drawTally() {
    if (!results.length) { clear(tally); return; }
    const good = results.filter((r) => r.ok).length;
    clear(tally, h("h3", "Nesta rodada"), h("p", { class: "tally" }, `${good} de ${results.length}`),
      h("ol", { class: "queue" }, results.map((r) => h("li", { class: r.ok ? "done" : "miss" },
        h("span", { class: "serif" }, r.word), r.ok ? null : h("span", { class: "sub" }, `você marcou ${r.chosen}`)))));
  }

  let trials = [];
  let i = 0;
  let results = [];
  let answered = false;
  let lastVoice = null;

  function pickVoice() {
    const voices = tts.listVoices(); // o Chrome carrega as vozes depois da página
    if (!voices.length) return null;
    const pool = voices.length > 1 ? voices.filter((v) => v !== lastVoice) : voices;
    lastVoice = pool[Math.floor(Math.random() * pool.length)];
    return lastVoice;
  }

  function build() {
    // A palavra tocada é sorteada: chutar sempre a mesma não funciona. No misturado, os sons se
    // revezam e os pares de cada som vêm embaralhados, para todos aparecerem.
    const shuffle = (a) => a.map((x) => [Math.random(), x]).sort((x, y) => x[0] - y[0]).map((x) => x[1]);
    const decks = sets.map((s) => shuffle(s.pairs.map((p) => ({ tag: s.tag, symbol: s.symbol, pair: p }))));
    const all = [];
    for (let k = 0; all.length < ROUND; k++) {
      const d = decks[k % decks.length];
      all.push(d[Math.floor(k / decks.length) % d.length]);
    }
    trials = Array.from({ length: ROUND }, (_, k) => {
      const t = all[k];
      const target = Math.random() < 0.5 ? 0 : 1;
      return { ...t, word: t.pair[target], other: t.pair[1 - target], voice: pickVoice(), rate: 0.85 + Math.random() * 0.15 };
    }).sort(() => Math.random() - 0.5);
    i = 0;
    results = [];
    drawTally();
  }

  // Antes de testar: ouvir os pares, cada palavra em duas vozes.
  function intro() {
    const pairs = sets.flatMap((s) => s.pairs.map((p) => [s, p]));
    clear(stage,
      h("h2", "Primeiro, ouça os pares"),
      h("p", { class: "soft", style: { margin: "6px 0 14px" } },
        "Clique nas palavras e repare no que muda. Quando a diferença ficar clara, comece."),
      h("ul", { class: "pairs" }, pairs.map(([s, p]) => h("li",
        mixed ? h("span", { class: "sym small muted" }, s.symbol) : null,
        p.map((w) => h("button", { class: "play pair-word", type: "button", onclick: () => tts.say(w, { voice: pickVoice(), rate: 0.85 }) }, `▶ ${w}`))))),
      h("div", { class: "row", style: { marginTop: "24px" } },
        h("button", { class: "btn", type: "button", onclick: () => { tts.unlock(); build(); trial(); } }, `Começar: ${ROUND} palavras`)));
  }

  function trial() {
    answered = false;
    const t = trials[i];
    const replay = () => tts.say(t.word, { voice: t.voice, rate: t.rate });
    const choices = h("div", { class: "choices", role: "group", "aria-label": "Qual palavra você ouviu?" },
      t.pair.map((w, k) => h("button", { class: "choice", type: "button", onclick: () => choose(w) },
        h("span", { class: "k" }, k ? "2 →" : "← 1"), h("b", w))));
    clear(stage,
      h("p", { class: "muted small" }, `${i + 1} de ${trials.length}`),
      h("div", { class: "progressbar" }, h("span", { style: { width: `${(100 * i) / trials.length}%` } })),
      h("p", { class: "soft" }, "Qual palavra você ouviu?"),
      choices,
      h("div", { class: "row", style: { marginTop: "16px" } },
        h("button", { class: "btn secondary small", type: "button", onclick: replay }, "▶ Ouvir de novo (R)")),
      h("div", { class: "result" }));
    t.replay = replay;
    setTimeout(() => { if (alive() && trials[i] === t && !answered) replay(); }, 250); // não fala na tela seguinte
  }

  async function choose(w) {
    if (answered) return;
    answered = true;
    tracker.bump();
    const t = trials[i];
    const ok = w === t.word;
    results.push({ ...t, chosen: w, ok });
    drawTally();
    stage.querySelectorAll(".choice").forEach((b) => {
      const word = b.querySelector("b").textContent;
      b.disabled = true;
      if (word === t.word) b.classList.add("right");
      else if (word === w) b.classList.add("wrong");
    });
    api("/api/listen/trial", { body: { tag: t.tag, word: t.word, other: t.other, chosen: w, voice: tts.voiceLabel(t.voice) } })
      .catch((e) => toast(e.message));
    const box = stage.querySelector(".result");
    const both = h("div", { class: "row", style: { marginTop: "10px" } },
      t.pair.map((x) => h("button", { class: "btn secondary small", type: "button", onclick: () => tts.say(x, { voice: t.voice, rate: t.rate }) }, `▶ ${x}`)),
      h("button", { class: "btn small", type: "button", onclick: next }, i < trials.length - 1 ? "Próxima (espaço)" : "Ver o resultado"));
    clear(box,
      h("p", { style: { color: ok ? "var(--mata)" : "var(--pitaya)", fontWeight: 700 } },
        ok ? `✓ Certo: ${t.word}` : `✗ Era ${t.word}. Você marcou ${w}.`),
      h("p", { class: "small muted" }, `Voz: ${tts.voiceLabel(t.voice)}. Compare as duas nesta mesma voz:`),
      both);
    // Acertou: segue sozinho, rápido. Errou: espera você comparar as duas palavras.
    if (ok) setTimeout(() => { if (answered && trials[i] === t && alive()) next(); }, 1100);
  }

  function next() {
    if (!answered || !stage.querySelector(".choices")) return; // o resultado já está na tela
    if (i < trials.length - 1) { i += 1; trial(); return; }
    finish();
  }

  function finish() {
    const good = results.filter((r) => r.ok).length;
    const misses = {};
    results.filter((r) => !r.ok).forEach((r) => {
      const k = `${r.word}|${r.chosen}`;
      misses[k] = misses[k] || { ...r, n: 0 };
      misses[k].n += 1;
    });
    const list = Object.values(misses).sort((a, b) => b.n - a.n);
    clear(stage,
      h("h2", `${good} de ${results.length} certas`),
      h("p", { class: "soft", style: { marginTop: "8px" } }, good === results.length
        ? "Nenhuma troca. Se continuar assim em outras rodadas, o ouvido já separa esses sons."
        : good / results.length >= 0.8 ? "O ouvido já separa quase sempre. As trocas abaixo são as que faltam."
        : "Ainda confunde bastante, e isso é normal no começo: o ouvido aprende com repetição, em dias diferentes."),
      list.length ? h("ul", { class: "list", style: { marginTop: "18px" } }, list.map((m) => h("li", { class: "row" },
        h("span", `Tocou `, h("b", { class: "serif" }, m.word), `, você marcou `, h("b", { class: "serif" }, m.chosen),
          m.n > 1 ? ` (${m.n}x)` : ""),
        m.pair.map((x) => h("button", { class: "play", type: "button", onclick: () => tts.say(x, { voice: m.voice, rate: 0.85 }) }, `▶ ${x}`))))) : null,
      h("div", { class: "row section", style: { marginTop: "24px" } },
        h("button", { class: "btn", type: "button", onclick: () => { build(); trial(); } }, "Mais uma rodada"),
        h("a", { class: "btn secondary", href: mixed ? "#/ouvir" : `#/treino/${sets[0].tag}` }, mixed ? "Escolher um som" : "Treinar a fala desse som"),
        h("a", { class: "btn quiet", href: "#/hoje" }, "Voltar para hoje")));
  }

  const onKey = (e) => {
    if (["TEXTAREA", "INPUT", "SELECT"].includes(document.activeElement.tagName) || e.ctrlKey || e.metaKey || e.altKey) return;
    const t = trials[i];
    if (!t || !stage.querySelector(".choices")) return;
    if (!answered && (e.key === "1" || e.key === "ArrowLeft")) choose(t.pair[0]);
    else if (!answered && (e.key === "2" || e.key === "ArrowRight")) choose(t.pair[1]);
    else if (e.key.toLowerCase() === "r") t.replay?.();
    else if (answered && (e.code === "Space" || e.key === "Enter")) { e.preventDefault(); next(); }
  };
  document.addEventListener("keydown", onKey);
  intro();
  return () => { document.removeEventListener("keydown", onKey); tracker.stop(); };
}
