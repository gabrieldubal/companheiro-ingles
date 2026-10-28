// Perguntar: dúvidas de inglês e pedidos para o app. A resposta conhece os seus dados e pode agir
// (cartões, palavras, frases de treino, som da vez, meta); cada ação tem botão de desfazer.
import { track } from "../lib/activity.js";
import { api } from "../lib/api.js";
import { clear, h, md, toast } from "../lib/dom.js";

const IDEAS = [
  "Por que eu erro o -s em \"the company uses\"? Me dá exemplos do meu trabalho.",
  "Como digo \"prazo final\" e \"cobrar alguém\" numa reunião?",
  "Me explica present perfect com os meus erros, e cria cartões.",
  "Quero treinar o th esta semana. Muda o som da vez e põe frases no treino.",
  "Prepara 5 cartões com palavras que eu uso no meu trabalho.",
];

export async function render(root, [prefill], alive) {
  const d = await api("/api/ask");
  if (!alive()) return;
  const tracker = track("perguntar");
  const messages = h("div", { class: "messages", "aria-live": "polite" });
  const input = h("textarea", { rows: 2, placeholder: "Pergunte em português ou em inglês. Enter envia; Shift+Enter quebra a linha.",
                                "aria-label": "Sua pergunta" });
  const send = h("button", { class: "btn", type: "button" }, "Enviar");
  const fresh = h("button", { class: "btn quiet small", type: "button" }, "Nova conversa");
  let busy = false;

  const chat = h("div", { class: "chat ask" },
    h("div", { class: "head" },
      h("div", h("h1", "Perguntar"),
        h("p", { class: "soft small", style: { marginTop: "4px" } },
          "Dúvidas de inglês e pedidos para o app. A resposta usa os seus erros, sons e cartões, e pode criar cartões, " +
          "guardar palavras e mudar o seu treino. Toda mudança tem botão de desfazer.")),
      fresh),
    messages,
    h("div", { class: "composer" }, h("div", { class: "typed" }, input, send)));

  // Com espaço na tela, as ideias ficam sempre ao lado; no celular, só na conversa vazia.
  function ideas(where = "inline") {
    return h("div", { class: `ideas ${where}` }, h("p", { class: "soft small" }, where === "inline" ? "Para começar:" : "Ideias de pergunta"),
      IDEAS.map((q) => h("button", { class: "idea", type: "button", onclick: () => { input.value = q; input.focus(); } }, q)));
  }
  root.append(h("div", { class: "bench" }, h("div", { class: "bench-main" }, chat),
    h("aside", { class: "bench-side side-ideas" }, h("div", { class: "side-block" }, ideas("side")),
      h("div", { class: "side-block" }, h("h3", "O que ele sabe de você"),
        h("p", { class: "small soft" }, "O seu perfil e objetivo, os sons fracos e o treino de ouvido, o caderno de gramática, as últimas correções, " +
          "as palavras guardadas e os cartões. " +
          "Tudo o que ele muda no app aparece embaixo da resposta, com Desfazer.")))));

  function actionLine(m, a, i) {
    if (a.type === "abrir") return h("li", h("a", { class: "btn small secondary", href: a.href }, a.label));
    const li = h("li", { class: a.undone ? "undone" : "" },
      h("span", { class: "mark" }, a.undone ? "↺" : "✓"), h("span", a.label));
    if (!a.undone && a.undo) {
      li.append(h("button", { class: "play", type: "button", onclick: async () => {
        try {
          const r = await api(`/api/ask/messages/${m.id}/actions/${i}/undo`, { body: {} });
          drawActions(r.message);
        } catch (e) { toast(e.message); }
      } }, "Desfazer"));
    } else if (a.undone) {
      li.append(h("span", { class: "small muted" }, "desfeito"));
    }
    return li;
  }

  const actionLists = new Map();
  function drawActions(m) {
    const ul = actionLists.get(m.id);
    if (ul) clear(ul, m.actions.map((a, i) => actionLine(m, a, i)));
  }

  function add(m) {
    if (m.role === "user") {
      messages.append(h("div", { class: "msg student" }, h("p", { class: "text" }, m.text)));
    } else {
      const ul = h("ul", { class: "did" });
      actionLists.set(m.id, ul);
      messages.append(h("div", { class: "msg teacher" }, md(m.text), m.actions.length ? ul : null));
      drawActions(m);
    }
    messages.scrollTop = messages.scrollHeight;
  }

  function draw(list) {
    clear(messages);
    actionLists.clear();
    if (!list.length) messages.append(ideas());
    list.forEach(add);
  }

  async function submit() {
    const text = input.value.trim();
    if (!text || busy) return;
    busy = true;
    send.disabled = true;
    tracker.bump();
    messages.querySelector(".ideas")?.remove();
    const mine = h("div", { class: "msg student pending" }, h("p", { class: "text" }, text));
    const t0 = Date.now();
    const wait = h("p", { class: "note" }, "Pensando…");
    const tick = setInterval(() => (wait.textContent = `Pensando… ${Math.round((Date.now() - t0) / 1000)} s`), 1000);
    messages.append(mine, wait);
    messages.scrollTop = messages.scrollHeight;
    try {
      const r = await api("/api/ask", { body: { text } });
      if (!alive()) return;
      mine.classList.remove("pending");
      wait.remove();
      input.value = "";
      add(r.message);
    } catch (e) {
      // A pergunta continua na caixa: é só enviar de novo.
      mine.remove();
      wait.remove();
      toast(e.message);
    } finally {
      clearInterval(tick);
      busy = false;
      send.disabled = false;
    }
  }

  send.onclick = submit;
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit(); }
  });
  fresh.onclick = async () => {
    try {
      await api("/api/ask/new", { body: {} });
      draw([]);
      input.focus();
    } catch (e) { toast(e.message); }
  };

  draw(d.messages);
  if (prefill) input.value = prefill;
  input.focus();
  return () => tracker.stop();
}
