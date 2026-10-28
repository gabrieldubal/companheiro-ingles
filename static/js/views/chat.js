// Conversa por voz com o tutor: cenários, correções em cartões, resumo no fim.
import { track } from "../lib/activity.js";
import { api, form } from "../lib/api.js";
import { compareButtons } from "../lib/audio.js";
import { bare, clear, h, plural, toast } from "../lib/dom.js";
import { createRecorder, extFor } from "../lib/recorder.js";
import { get, set } from "../lib/store.js";
import * as tts from "../lib/tts.js";
import { app } from "../main.js";
import { describe } from "./common.js";

export async function render(root, [scenarioId, mode]) {
  const cfg = app.config;
  if (!scenarioId) return renderPicker(root, cfg);
  const sc = cfg.scenarios.find((s) => s.id === scenarioId);
  if (!sc) { location.hash = "#/conversar"; return; }
  return renderChat(root, cfg, sc, mode === "escrever");
}

// Os cenários agrupados pelo que você quer treinar, com a sugestão do dia marcada.
// Os cenários da pessoa (data/cenarios.json) vêm num grupo próprio, antes destes.
const GROUPS = [
  ["Para o dia a dia", ["livre", "viagem"]],
  ["Para o trabalho", ["trabalho", "entrevista"]],
  ["Para conversar sobre ideias", ["ideias"]],
  ["Para medir o seu nível", ["diagnostico"]],
];

async function renderPicker(root, cfg) {
  const level = h("select", { id: "level" }, cfg.levels.map((l) =>
    h("option", { value: l.value, selected: l.value === get("level", cfg.default_level) }, l.label)));
  level.onchange = () => set("level", parseFloat(level.value));
  let suggested = null;
  try {
    suggested = (await api("/api/today")).steps.find((s) => s.kind === "conversa")?.scenario;
  } catch {}
  const byId = Object.fromEntries(cfg.scenarios.map((s) => [s.id, s]));
  const listed = new Set(GROUPS.flatMap(([, ids]) => ids));
  const mine = cfg.scenarios.filter((s) => s.custom).map((s) => s.id);
  const groups = [["Os seus cenários", mine], ...GROUPS.map(([title, ids]) => [title, ids.filter((id) => byId[id])])];
  const rest = cfg.scenarios.filter((s) => !s.custom && !listed.has(s.id)).map((s) => s.id); // cenário novo em tutor.py
  if (rest.length) groups.push(["Outros", rest]);
  root.append(
    h("header", h("h1", "Conversar"),
      h("p", "Escolha a conversa. O tutor conhece o seu perfil e puxa os erros que estão na hora de revisar.")),
    h("label", { class: "field" }, h("span", "Seu nível"), level),
    h("div", { class: "scenario-groups" }, groups.filter(([, ids]) => ids.length).map(([title, ids]) =>
      h("section", { class: "scenario-group" }, h("h2", title),
        ids.map((id) => h("a", { class: "scenario-link", href: `#/conversar/${id}` },
          h("strong", byId[id].title, id === suggested ? h("span", { class: "chip" }, "sugestão de hoje") : null),
          h("span", byId[id].subtitle)))))));
}

// silent: conversa por escrito (no trabalho): a caixa de texto já aberta e nada lido em voz alta.
function renderChat(root, cfg, sc, silent = false) {
  const level = get("level", cfg.default_level);
  // alive cai para false quando você sai da tela: nada que chegue depois (resposta do tutor,
  // erro, contador de tempo) pode agir sobre a tela seguinte.
  const st = { id: null, ended: false, busy: false, lastReply: "", tracker: null, alive: true };
  const messages = h("div", { class: "messages", "aria-live": "polite" });
  const status = h("span", { class: "muted small" });
  const endBtn = h("button", { class: "btn secondary small", type: "button" }, "Encerrar e ver o resumo");
  const textBox = h("textarea", { placeholder: "Escreva em inglês, ou pergunte: how do I say...?", rows: 2 });
  const sendBtn = h("button", { class: "btn small", type: "button" }, "Enviar");
  const typed = h("div", { class: "typed", hidden: !silent }, textBox, sendBtn);
  const keyboardBtn = h("button", { class: "btn quiet", type: "button" }, silent ? "Esconder a caixa de texto" : "Escrever em vez de falar");
  const repeatBtn = h("button", { class: "btn quiet", type: "button", onclick: () => tts.speak(st.lastReply) }, "Ouvir de novo");
  const recorder = createRecorder({ raw: false, onBlob: handleAudio });
  // Uma faixa só: microfone, dica e as duas ações. A caixa de texto aparece embaixo só se pedir.
  const composer = h("footer", { class: "composer" },
    h("div", { class: "bar" }, recorder.el, repeatBtn, keyboardBtn), typed);
  // "Nesta conversa": o que a conversa já rendeu, juntado (com espaço na tela; no celular, as
  // mesmas coisas estão nas mensagens). Clicar numa correção leva até a resposta dela.
  const log = { fixes: [], words: [], good: [], unsure: [], patterns: {} };
  const sideFixes = h("div", { class: "side-block" });
  const sidePatterns = h("div", { class: "side-block" });
  const sideWords = h("div", { class: "side-block" });
  const sideMore = h("div", { class: "side-block" });
  const sideRecurring = h("div", { class: "side-block" });
  const label = (pat) => cfg.pattern_pt?.[pat] || pat;
  function drawSide() {
    clear(sideFixes, h("h3", "Correções", log.fixes.length ? h("span", { class: "small muted" }, ` (${log.fixes.length})`) : null),
      log.fixes.length
        ? h("div", { class: "fixes", style: { marginTop: "6px" } }, log.fixes.slice().reverse().map(({ c, at }) =>
            h("div", { class: "fix", title: "Ir até a resposta", onclick: () => at.scrollIntoView({ behavior: "smooth", block: "center" }) },
              h("p", { class: "line" }, h("del", c.original), "  ", h("ins", c.better)), h("p", { class: "tag" }, label(c.pattern)))))
        : h("p", { class: "small muted" }, "Aparecem aqui conforme você responde."));
    const top = Object.entries(log.patterns).sort((a, b) => b[1] - a[1]).slice(0, 5);
    clear(sidePatterns, top.length ? [h("h3", "O que mais apareceu"),
      h("p", { class: "small soft" }, top.map(([pat, n]) => `${label(pat)} (${n}×)`).join(", ") + ".")] : null);
    clear(sideWords, log.words.length ? [h("h3", "Palavras novas"), log.words.map((w) =>
      h("div", { class: "word-card", onclick: () => tts.speak(`${w.word}. ${w.example}`) }, h("strong", w.word), ` ${w.meaning_pt}`, h("em", w.example)))] : null);
    clear(sideMore,
      log.good.length ? h("p", { class: "small" }, h("b", "Acertou: "), [...new Set(log.good.map(label))].join(", "), ".") : null,
      log.unsure.length ? h("p", { class: "small", style: { marginTop: "6px" } }, h("b", "Pronúncia a conferir: "), [...new Set(log.unsure)].join(", "), ".") : null);
  }
  root.append(h("div", { class: "bench" },
    h("div", { class: "bench-main" }, h("div", { class: "chat" },
      h("div", { class: "head" },
        h("div", h("p", { class: "date-line" }, h("a", { href: "#/conversar" }, "Conversar")), h("h2", sc.title), status),
        endBtn),
      messages, composer)),
    h("aside", { class: "bench-side chat-side" },
      h("div", { class: "side-block" }, h("h3", "Nesta conversa"), h("p", { class: "small soft" }, sc.subtitle)),
      sideRecurring, sideFixes, sidePatterns, sideWords, sideMore)));
  drawSide();

  keyboardBtn.onclick = () => {
    typed.hidden = !typed.hidden;
    keyboardBtn.textContent = typed.hidden ? "Escrever em vez de falar" : "Esconder a caixa de texto";
    if (!typed.hidden) textBox.focus();
  };
  sendBtn.onclick = submitTyped;
  textBox.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submitTyped(); }
  });
  endBtn.onclick = endSession;

  let timer = null;
  function busy(on, label = "") {
    st.busy = on;
    recorder.setBusy(on, label);
    sendBtn.disabled = on;
    clearInterval(timer);
    if (!on) { status.textContent = ""; return; }
    const t0 = Date.now();
    status.textContent = label;
    timer = setInterval(() => (status.textContent = `${label} ${Math.round((Date.now() - t0) / 1000)} s`), 1000);
  }

  const scroll = () => requestAnimationFrame(() => (messages.scrollTop = messages.scrollHeight));
  const note = (text) => { messages.append(h("p", { class: "note" }, text)); scroll(); };

  function addTutor(turn) {
    const pt = h("p", { class: "translation", hidden: true }, turn.reply_pt);
    const card = h("div", { class: "msg tutor" }, h("p", { class: "text" }, turn.reply), pt,
      h("div", { class: "actions" },
        h("button", { class: "play", type: "button", onclick: () => tts.speak(turn.reply) }, "▶ ouvir"),
        h("button", { class: "play", type: "button", onclick: () => (pt.hidden = !pt.hidden) }, "traduzir")),
      (turn.new_words || []).map((w) => h("div", { class: "word-card", onclick: () => tts.speak(`${w.word}. ${w.example}`) },
        h("strong", w.word), ` ${w.meaning_pt}`, h("em", w.example))));
    messages.append(card);
    scroll();
    const fresh = (turn.new_words || []).filter((w) => !log.words.some((x) => x.word === w.word));
    if (fresh.length) { log.words.push(...fresh); drawSide(); }
    st.lastReply = turn.reply;
    if (!silent && get("autoSpeak", true)) tts.speak(turn.reply);
  }

  function addStudent(text, words) {
    const p = h("p");
    if (words?.length) {
      words.forEach((w, i) => {
        if (i) p.append(" ");
        p.append(w.unsure ? h("span", { class: "unsure", title: "O Whisper teve dúvida aqui. Clique para ouvir a versão nativa.",
                                       onclick: () => tts.speak(bare(w.w)) }, w.w) : w.w);
      });
    } else {
      p.textContent = text;
    }
    const bubble = h("div", { class: "msg student" }, p);
    messages.append(bubble);
    scroll();
    return bubble;
  }

  function addFeedback(bubble, turn, unsure) {
    const box = h("div", { class: "feedback" });
    if (!turn.corrections.length) box.append(h("p", { class: "meta" }, "Sem correções nesta resposta."));
    turn.corrections.forEach((c) => box.append(h("div", { class: "fix" },
      h("p", { class: "line" }, h("del", c.original), "  ", h("ins", c.better), " ",
        h("button", { class: "play", type: "button", onclick: () => tts.speak(c.better) }, "▶")),
      h("p", { class: "why" }, c.explanation_pt),
      h("p", { class: "tag" }, cfg.pattern_pt?.[c.pattern] || c.pattern))));
    const carded = new Set(turn.corrections.map((c) => c.pattern));
    const extra = (turn.pattern_counts || []).filter((pc) => pc.count > 1 || !carded.has(pc.pattern));
    if (extra.length) box.append(h("p", { class: "meta" }, "Nesta resposta também: " +
      extra.map((pc) => `${cfg.pattern_pt?.[pc.pattern] || pc.pattern} (${pc.count}×)`).join(", ") + "."));
    if (unsure.length) box.append(h("p", { class: "meta" }, `Pronúncia a conferir: ${unsure.join(", ")}.`));
    (turn.good_uses || []).forEach((g) => box.append(h("p", { class: "meta" }, `Acertou: ${cfg.pattern_pt?.[g] || g}.`)));
    bubble.after(box);
    turn.corrections.forEach((c) => log.fixes.push({ c, at: bubble }));
    (turn.pattern_counts || []).forEach((pc) => { log.patterns[pc.pattern] = (log.patterns[pc.pattern] || 0) + pc.count; });
    log.good.push(...(turn.good_uses || []));
    log.unsure.push(...unsure);
    drawSide();
    scroll();
  }

  async function start() {
    busy(true, "Preparando a conversa…");
    try {
      const r = await api("/api/sessions", { body: { scenario: sc.id, level } });
      if (!st.alive) return;
      st.id = r.session_id;
      tts.setDefaultRate(r.tts_rate);
      st.tracker = track("conversa", sc.id);
      if (r.recurring?.length) {
        note(`Hoje o tutor vai criar chances de praticar: ${r.recurring.map((x) => cfg.pattern_pt?.[x.pattern] || x.pattern).join(", ")}.`);
        clear(sideRecurring, h("h3", "O tutor vai puxar"), h("p", { class: "small soft" }, r.recurring.map((x) => label(x.pattern)).join(", ") + "."));
      }
      addTutor(r.turn);
    } catch (e) {
      if (!st.alive) return;
      toast(e.message);
      location.hash = "#/conversar";
    } finally {
      if (st.alive) busy(false);
    }
  }

  async function handleAudio(blob) {
    if (!st.id || st.ended) return;
    st.tracker?.bump();
    busy(true, "Transcrevendo…");
    let r = null;
    try {
      r = await api("/api/transcribe", { body: form({
        file: [blob, `fala.${extFor(blob)}`], save: get("saveAudio", true) ? "true" : "false", session_id: st.id,
      }) });
      if (!r.text && st.alive) toast("Não entendi nada no áudio. Tente de novo.");
    } catch (e) {
      if (st.alive) toast(e.message);
    } finally {
      busy(false);
    }
    if (!r?.text || !st.alive) return;
    const meta = { transcript: r.text, words: r.words, recording_id: r.recording_id };
    if (get("review", false)) {
      typed.hidden = false;
      keyboardBtn.textContent = "Esconder a caixa de texto";
      textBox.value = r.text;
      st.pending = meta;
      textBox.focus();
    } else {
      sendText(r.text, meta);
    }
  }

  function submitTyped() {
    tts.unlock();
    if (st.busy || !st.id || st.ended) {
      toast("Espere o tutor terminar de responder para enviar.");
      return; // o texto fica na caixa
    }
    const text = textBox.value;
    textBox.value = "";
    const meta = st.pending || {};
    st.pending = null;
    sendText(text, meta);
  }

  async function sendText(text, meta = {}) {
    text = (text || "").trim();
    if (!text || !st.id || st.busy || st.ended) return;
    st.tracker?.bump();
    const words = meta.words && meta.transcript === text ? meta.words : null;
    const unsure = words ? words.filter((w) => w.unsure).map((w) => bare(w.w)) : [];
    const bubble = addStudent(text, words);
    busy(true, "Pensando…");
    try {
      const r = await api(`/api/sessions/${st.id}/messages`, { body: { text, recording_id: meta.recording_id || null, unsure } });
      if (!st.alive) return;
      addFeedback(bubble, r.turn, unsure);
      addTutor(r.turn);
    } catch (e) {
      if (!st.alive) return;
      toast(e.message);
      const retry = h("button", { class: "play", type: "button" }, "tentar de novo");
      retry.onclick = () => { bubble.remove(); sendText(text, meta); };
      bubble.append(h("div", { class: "actions" }, retry));
    } finally {
      busy(false);
    }
  }

  async function endSession() {
    if (!st.id || st.ended) { location.hash = "#/conversar"; return; }
    recorder.stop(true);
    tts.stop();
    busy(true, "Fazendo o resumo…");
    try {
      const r = await api(`/api/sessions/${st.id}/end`, { body: {} });
      if (!st.alive) return;
      st.ended = true;
      st.tracker?.stop();
      composer.hidden = true;
      endBtn.hidden = true;
      renderSummary(r.summary);
    } catch (e) {
      toast(e.message);
    } finally {
      busy(false);
    }
  }

  function renderSummary(s) {
    const card = h("div", { class: "summary" }, h("h3", "Resumo"), h("p", s.summary_pt));
    if (s.cefr_estimate) {
      card.append(h("p", { style: { marginTop: "10px" } }, h("b", `Nível estimado: ${s.cefr_estimate}`),
        s.scale_estimate ? ` (≈ ${s.scale_estimate} na sua escala de 1 a 4)` : ""),
        h("p", { class: "small muted" }, s.level_comment_pt));
    }
    if (s.went_well_pt?.length) card.append(h("h4", "Foi bem"), h("ul", s.went_well_pt.map((w) => h("li", w))));
    if (s.focus_pt) card.append(h("h4", "Para a próxima"), h("p", s.focus_pt));
    if (s.best_sentences?.length) {
      card.append(h("h4", "Suas frases, do jeito nativo (clique para ouvir e repita)"),
        s.best_sentences.map((b) => h("blockquote", { onclick: () => tts.speak(b) }, b)));
    }
    const pronBox = h("div");
    card.append(h("h4", "Pronúncia nesta conversa"), pronBox,
      h("div", { class: "row", style: { marginTop: "18px" } },
        h("a", { class: "btn", href: "#/hoje" }, "Voltar para hoje"),
        h("a", { class: "btn secondary", href: "#/erros" }, "Ver meus erros")));
    messages.append(card);
    scroll();
    loadPron(pronBox, 0);
  }

  async function loadPron(box, tries) {
    try {
      const p = await api(`/api/sessions/${st.id}/pron`);
      if (!p.recordings) {
        clear(box, h("p", { class: "soft" }, "Nenhum áudio guardado nesta conversa. Ligue a opção em Ajustes para o app analisar a sua pronúncia."));
        return;
      }
      if (p.pron !== "pronto" && !p.sounds.length) {
        clear(box, h("p", { class: "soft" }, `Detector de pronúncia: ${p.pron}. Os áudios ficaram guardados e serão analisados quando ele ligar.`));
        return;
      }
      if (p.pending && tries < 12) {
        clear(box, h("p", { class: "soft" }, `Analisando ${plural(p.pending, "gravação", "gravações")}…`));
        setTimeout(() => box.isConnected && loadPron(box, tries + 1), 5000);
        return;
      }
      const off = p.sounds.filter((s) => s.off);
      clear(box, off.length
        ? h("ul", { class: "evidence" }, p.off.slice(0, 6).map((c) =>
            h("li", h("span", { class: "w" }, c.word), h("span", { class: "small soft" }, describe(c)),
              compareButtons(c.word, c.recording_id, c.start, c.end))))
        : h("p", { class: "soft" }, "Nenhum som fora do padrão nas palavras que o detector conseguiu julgar."));
    } catch (e) {
      clear(box, h("p", { class: "muted" }, e.message));
    }
  }

  start();
  return () => {
    st.alive = false;
    clearInterval(timer);
    recorder.stop(true);
    st.tracker?.stop();
  };
}
