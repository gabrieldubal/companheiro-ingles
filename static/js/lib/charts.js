// Gráficos pequenos em SVG, feitos à mão.
// Regras (skill de visualização): uma série por gráfico, colunas de no máximo 24 px com
// topo arredondado de 4 px, linha de 2 px, ponto final com anel na cor do fundo, grade em
// fio sólido, referência sólida na cor do texto, tooltip em cada marca e tabela para quem
// não enxerga o gráfico. Verde e pitaya nunca aparecem como duas séries no mesmo gráfico.
import { h } from "./dom.js";

const NS = "http://www.w3.org/2000/svg";
function s(tag, attrs = {}, ...kids) {
  const el = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) if (v !== undefined && v !== null) el.setAttribute(k, v);
  kids.flat().forEach((k) => {
    if (k === null || k === undefined || k === false) return; // 0 é valor: o tique "0" tem que aparecer
    el.append(k instanceof Node ? k : document.createTextNode(String(k)));
  });
  return el;
}

function niceMax(v) {
  if (v <= 0) return 1;
  const p = Math.pow(10, Math.floor(Math.log10(v)));
  for (const m of [1, 2, 2.5, 5, 10]) if (m * p >= v) return m * p;
  return 10 * p;
}

function tooltipLayer(wrap) {
  const tip = h("div", { class: "tooltip", hidden: true });
  wrap.append(tip);
  return {
    show(x, y, value, label) {
      tip.replaceChildren(h("b", value), document.createElement("br"), label);
      tip.style.left = `${x}px`;
      tip.style.top = `${y}px`;
      tip.hidden = false;
    },
    hide() { tip.hidden = true; },
  };
}

function tableView(headers, rows) {
  return h("details", { class: "table-view" }, h("summary", "Ver os números"),
    h("table", { class: "data" },
      h("thead", h("tr", headers.map((x) => h("th", x)))),
      h("tbody", rows.map((r) => h("tr", r.map((c) => h("td", c)))))));
}

const roundTop = (x, y, w, hgt, r) => {
  r = Math.min(r, w / 2, hgt);
  return `M${x},${y + hgt} V${y + r} Q${x},${y} ${x + r},${y} H${x + w - r} Q${x + w},${y} ${x + w},${y + r} V${y + hgt} Z`;
};

// O SVG é desenhado na largura real do cartão (e redesenhado quando ela muda): assim o texto
// fica sempre do mesmo tamanho, em vez de crescer no monitor grande e virar formiga no celular.
function responsive(wrap, svg, draw, fallback) {
  let w = 0;
  const redraw = (width) => {
    const W = Math.max(240, Math.round(width));
    if (Math.abs(W - w) < 4) return;
    w = W;
    svg.replaceChildren();
    draw(svg, W);
  };
  redraw(fallback);
  if ("ResizeObserver" in window) {
    let frame = 0;
    let attached = false;
    const ro = new ResizeObserver((entries) => {
      if (!wrap.isConnected) { if (attached) ro.disconnect(); return; } // esteve na tela e saiu: a tela mudou
      attached = true;
      const width = entries[0].contentRect.width;
      if (!width) return;
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => redraw(width));
    });
    ro.observe(wrap);
  }
}

/**
 * Colunas: data = [{label, value, tip}], ref = {value, label} (linha de meta).
 * color: "good" | "bad". format(v) formata o valor.
 */
export function columns({ data, ref, color = "good", format = (v) => v, unit = "", height = 180 }) {
  const svg = s("svg", { role: "img" });
  const wrap = h("div", { class: "chart" }, svg);
  const tip = tooltipLayer(wrap);
  const fill = color === "bad" ? "var(--chart-bad)" : "var(--chart-good)";
  const max = niceMax(Math.max(ref?.value || 0, ...data.map((d) => d.value)) * 1.1);
  responsive(wrap, svg, (svg, W) => {
    const H = height, padL = 34, padB = 26, padT = 18;
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    const y = (v) => padT + (H - padT - padB) * (1 - v / max);
    const band = (W - padL) / data.length;
    const bw = Math.min(24, band * 0.5);
    // Coluna estreita (celular, muitas sessões): rótulo de duas em duas (ou mais), sempre com a última.
    // A largura do rótulo sai do maior texto, na letra do eixo (0,72rem, ~0,6 em por caractere).
    const charW = 0.6 * 0.72 * parseFloat(getComputedStyle(document.documentElement).fontSize);
    const labelW = Math.max(...data.map((d) => String(d.label).length)) * charW + 10;
    const every = Math.max(1, Math.ceil(labelW / band));
    const labeled = (i) => i === data.length - 1 || (i % every === 0 && data.length - 1 - i >= every);
    const grid = s("g", { class: "grid" });
    const axis = s("g", { class: "axis" });
    for (const t of [0, max / 2, max]) {
      grid.append(s("line", { x1: padL, x2: W, y1: y(t), y2: y(t) }));
      axis.append(s("text", { x: padL - 8, y: y(t) + 4, "text-anchor": "end" }, format(t)));
    }
    svg.append(grid, axis);
    data.forEach((d, i) => {
      const cx = padL + band * i + band / 2;
      const top = y(d.value);
      if (d.value > 0) svg.append(s("path", { d: roundTop(cx - bw / 2, top, bw, H - padB - top, 4), fill }));
      if (labeled(i)) axis.append(s("text", { x: cx, y: H - 8, "text-anchor": "middle" }, d.label));
      const hit = s("rect", { class: "hit", x: cx - band / 2, y: padT, width: band, height: H - padT - padB, tabindex: 0 });
      const show = () => {
        const r = svg.getBoundingClientRect();
        tip.show((cx / W) * r.width, (top / H) * r.height, `${format(d.value)}${unit}`, d.tip || d.label);
      };
      hit.addEventListener("pointermove", show);
      hit.addEventListener("focus", show);
      hit.addEventListener("pointerleave", tip.hide);
      hit.addEventListener("blur", tip.hide);
      svg.append(hit);
    });
    if (ref) {
      // Rótulo da meta na ponta esquerda: na direita ele batia no valor da última coluna.
      svg.append(s("line", { class: "ref", x1: padL, x2: W, y1: y(ref.value), y2: y(ref.value) }));
      svg.append(s("text", { class: "ref-label", x: padL + 6, y: y(ref.value) - 6, "text-anchor": "start" }, ref.label));
    }
    const last = data[data.length - 1];
    if (last && last.value > 0) {
      const cx = padL + band * (data.length - 1) + band / 2;
      svg.append(s("text", { class: "val", x: cx, y: y(last.value) - 6, "text-anchor": "middle" }, format(last.value)));
    }
  }, 560);
  wrap.append(tableView(["", "valor"], data.map((d) => [d.tip || d.label, `${format(d.value)}${unit}`])));
  return wrap;
}

/**
 * Linha: points = [{label, value, tip}], ref = {value, label} (ex.: ruído dos nativos).
 * Crosshair encontra o ponto mais próximo no eixo x.
 */
export function line({ points, ref, color = "bad", format = (v) => v, max, height = 150 }) {
  const svg = s("svg", { role: "img" });
  const wrap = h("div", { class: "chart" }, svg);
  const tip = tooltipLayer(wrap);
  const stroke = color === "bad" ? "var(--chart-bad)" : "var(--chart-good)";
  const top = max ?? niceMax(Math.max(ref?.value || 0, ...points.map((p) => p.value)) * 1.15);
  const n = points.length;
  responsive(wrap, svg, (svg, W) => {
    const H = height, padL = 34, padB = 24, padT = 14, padR = 14;
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    const x = (i) => (n === 1 ? (padL + W - padR) / 2 : padL + ((W - padL - padR) * i) / (n - 1));
    const y = (v) => padT + (H - padT - padB) * (1 - v / top);
    const grid = s("g", { class: "grid" });
    const axis = s("g", { class: "axis" });
    for (const t of [0, top / 2, top]) {
      grid.append(s("line", { x1: padL, x2: W - padR, y1: y(t), y2: y(t) }));
      axis.append(s("text", { x: padL - 8, y: y(t) + 4, "text-anchor": "end" }, format(t)));
    }
    svg.append(grid, axis);
    if (ref) {
      // Na esquerda, longe do rótulo do último ponto (que fica na direita).
      svg.append(s("line", { class: "ref", x1: padL, x2: W - padR, y1: y(ref.value), y2: y(ref.value) }));
      svg.append(s("text", { class: "ref-label", x: padL + 6, y: y(ref.value) - 6, "text-anchor": "start" }, ref.label));
    }
    if (n > 1) {
      const d = points.map((p, i) => `${i ? "L" : "M"}${x(i)},${y(p.value)}`).join(" ");
      svg.append(s("path", { d, fill: "none", stroke, "stroke-width": 2, "stroke-linejoin": "round", "stroke-linecap": "round" }));
    }
    points.forEach((p, i) => {
      const last = i === n - 1;
      if (last || n <= 6) {
        svg.append(s("circle", { cx: x(i), cy: y(p.value), r: last ? 5 : 4, fill: stroke, stroke: "var(--surface)", "stroke-width": 2 }));
      }
    });
    if (n) {
      const lp = points[n - 1];
      svg.append(s("text", { class: "val", x: x(n - 1), y: y(lp.value) - 10, "text-anchor": n === 1 ? "middle" : "end" }, format(lp.value)));
    }
    // O segundo rótulo só entra se couber entre o primeiro e ele (os dois saem da ponta para dentro).
    const charW = 0.6 * 0.72 * parseFloat(getComputedStyle(document.documentElement).fontSize);
    const labelW = Math.max(...points.map((p) => String(p.label).length), 1) * charW + 10;
    const ticks = n > 2 && x(1) - x(0) >= 2 * labelW ? [0, 1, n - 1] : [0, n - 1];
    ticks.filter((v, i, a) => v >= 0 && v < n && a.indexOf(v) === i).forEach((i) => {
      axis.append(s("text", { x: x(i), y: H - 6, "text-anchor": n === 1 ? "middle" : i === 0 ? "start" : "end" }, points[i].label));
    });
    const cross = s("line", { x1: 0, x2: 0, y1: padT, y2: H - padB, stroke: "var(--ink-3)", "stroke-width": 1, visibility: "hidden" });
    svg.append(cross);
    const hit = s("rect", { class: "hit", x: padL, y: padT, width: W - padL - padR, height: H - padT - padB, tabindex: 0 });
    const nearest = (clientX) => {
      const r = svg.getBoundingClientRect();
      const vx = ((clientX - r.left) / r.width) * W;
      let best = 0;
      points.forEach((_, i) => { if (Math.abs(x(i) - vx) < Math.abs(x(best) - vx)) best = i; });
      return best;
    };
    const showAt = (i) => {
      const r = svg.getBoundingClientRect();
      cross.setAttribute("x1", x(i)); cross.setAttribute("x2", x(i)); cross.setAttribute("visibility", "visible");
      const p = points[i];
      tip.show((x(i) / W) * r.width, (y(p.value) / H) * r.height, format(p.value), p.tip || p.label);
    };
    hit.addEventListener("pointermove", (e) => n && showAt(nearest(e.clientX)));
    hit.addEventListener("focus", () => n && showAt(n - 1));
    const hide = () => { tip.hide(); cross.setAttribute("visibility", "hidden"); };
    hit.addEventListener("pointerleave", hide);
    hit.addEventListener("blur", hide);
    svg.append(hit);
  }, 360);
  wrap.append(tableView(["", "valor"], points.map((p) => [p.tip || p.label, format(p.value)])));
  return wrap;
}

/** Barra de taxa: a sua (preenchida) e a dos nativos (traço), identificadas por texto.
 *  legend: false nas listas, onde a explicação do traço aparece uma vez só, em cima. */
export function rateBar(rate, native, { label, legend = true } = {}) {
  const scale = (v) => `${Math.min(100, Math.round(100 * v))}%`;
  return h("div", { class: "rate", role: "img", "aria-label": label || `Você ${scale(rate)}, nativos ${scale(native)}` },
    h("div", { class: "track" },
      h("span", { class: "fill", style: { width: scale(rate) } }),
      h("span", { class: "native", style: { left: scale(native) } })),
    h("span", { class: "small" }, scale(rate)),
    legend ? h("span", { class: "legend" }, `Você: ${scale(rate)}. O traço marca os nativos: ${scale(native)}.`) : null);
}
