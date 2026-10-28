// Montagem de DOM sem innerHTML: todo texto entra como texto (o que vem do Claude também).

export function h(tag, attrs, ...children) {
  const el = document.createElement(tag);
  // Segundo argumento que não é objeto de atributos (texto, número, nó, lista) é filho. Inclusive 0.
  if (attrs !== null && attrs !== undefined && (typeof attrs !== "object" || attrs instanceof Node || Array.isArray(attrs))) {
    children.unshift(attrs);
    attrs = null;
  }
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") el.className = v;
    else if (k === "text") el.textContent = v;
    else if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2), v);
    else if (k === "style" && typeof v === "object") Object.assign(el.style, v);
    else el.setAttribute(k, v === true ? "" : v);
  }
  append(el, children);
  return el;
}

function append(el, children) {
  for (const c of children.flat(Infinity)) {
    if (c === null || c === undefined || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
}

export const $ = (sel, root = document) => root.querySelector(sel);

export function clear(node, ...children) {
  node.replaceChildren();
  append(node, children);
  return node;
}

const WEEKDAYS = ["domingo", "segunda", "terça", "quarta", "quinta", "sexta", "sábado"];
const MONTHS = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro",
  "outubro", "novembro", "dezembro"];

export function longDate(d = new Date()) {
  return `${WEEKDAYS[d.getDay()]}, ${d.getDate()} de ${MONTHS[d.getMonth()]}`;
}

export function shortDate(iso) {
  const d = new Date(iso);
  return d.toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
}

export function dayMonth(iso) {
  const d = new Date(iso.length <= 10 ? iso + "T12:00:00" : iso);
  return `${d.getDate()}/${d.getMonth() + 1}`;
}

export const pct = (x) => `${Math.round(100 * x)}%`;

export function plural(n, one, many) {
  return `${n} ${n === 1 ? one : many}`;
}

let toastTimer;
export function toast(msg, ms = 5000) {
  const t = $("#toast");
  t.textContent = msg;
  t.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (t.hidden = true), ms);
}

export const bare = (w) => String(w).replace(/[^\w'-]/g, "");

// "it's it's lower" vira "it's lower": a repetição da fala não é o erro, e só confunde na hora de ler.
export const collapseRepeats = (s) => String(s || "").replace(/\b([\w']+)(?:\s+\1\b)+/gi, "$1");

// Markdown curto (o que a resposta do Perguntar usa), montado como DOM: **negrito**, *itálico*,
// `código`, listas com "- " ou "1. " e parágrafos. Nada vira HTML cru.
function inline(text) {
  const out = [];
  // Sem _itálico_ nem __negrito__: o sublinhado aqui é lacuna de exercício ("I ____ here").
  const re = /(\*\*[^*\n]+\*\*|\*[^*\s][^*\n]*\*|`[^`\n]+`)/g;
  let last = 0;
  for (const m of text.matchAll(re)) {
    if (m.index > last) out.push(text.slice(last, m.index));
    const t = m[0];
    if (t.startsWith("**")) out.push(h("strong", t.slice(2, -2)));
    else if (t.startsWith("`")) out.push(h("code", t.slice(1, -1)));
    else out.push(h("em", t.slice(1, -1)));
    last = m.index + t.length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

export function md(text) {
  const box = h("div", { class: "md" });
  // Linha a linha: "Veja:\n- a\n- b" vira parágrafo + lista, e uma lista numerada separada por
  // linhas em branco continua a contagem (start) em vez de recomeçar do 1.
  for (const block of String(text || "").trim().split(/\n\s*\n/)) {
    let list = null;
    let para = null;
    for (const raw of block.split("\n")) {
      const line = raw.trim();
      if (!line) continue;
      const bullet = line.match(/^[-*•]\s+(.*)$/);
      const num = line.match(/^(\d+)[.)]\s+(.*)$/);
      if (bullet || num) {
        const tag = bullet ? "UL" : "OL";
        if (!list || list.tagName !== tag) {
          list = h(tag.toLowerCase());
          if (num && Number(num[1]) > 1) list.start = Number(num[1]);
          box.append(list);
        }
        list.append(h("li", inline(bullet ? bullet[1] : num[2])));
        para = null;
      } else {
        list = null;
        if (para) para.append(h("br"));
        else { para = h("p"); box.append(para); }
        para.append(...inline(line.replace(/^#+\s*/, "")));
      }
    }
  }
  return box;
}
