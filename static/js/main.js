// Roteador por hash (#/hoje, #/treino/th-voiceless...). Cada tela exporta render(root, params)
// e pode devolver uma função de limpeza, chamada ao sair dela.
import { api, token } from "./lib/api.js";
import { $, clear, h } from "./lib/dom.js";
import * as tts from "./lib/tts.js";

const ROUTES = {
  hoje: () => import("./views/today.js"),
  conversar: () => import("./views/chat.js"),
  pronuncia: () => import("./views/pronunciation.js"),
  treino: () => import("./views/drill.js"),
  leitura: () => import("./views/reading.js"),
  "fale-certo": () => import("./views/speakright.js"),
  erros: () => import("./views/errors.js"),
  progresso: () => import("./views/progress.js"),
  historico: () => import("./views/history.js"),
  ajustes: () => import("./views/settings.js"),
  mais: () => import("./views/more.js"),
  frases: () => import("./views/phrases.js"),
  corrigir: () => import("./views/ladder.js"),
  cartoes: () => import("./views/cards.js"),
  perguntar: () => import("./views/ask.js"),
  ouvir: () => import("./views/listen.js"),
  imitar: () => import("./views/shadow.js"),
  usar: () => import("./views/use.js"),
  entender: () => import("./views/learn.js"),
  "boas-vindas": () => import("./views/welcome.js"),
};
// No celular, ficam em "Mais".
const IN_MORE = new Set(["perguntar", "entender", "fale-certo", "erros", "progresso", "historico", "ajustes", "mais"]);

export const app = { config: null };
let cleanup = null;
let seq = 0;

async function route() {
  const [name, ...params] = (location.hash.replace(/^#\/?/, "") || "hoje").split("/");
  const key = ROUTES[name] ? name : "hoje";
  const nav = ["treino", "leitura", "frases", "corrigir", "ouvir", "imitar"].includes(key) ? "pronuncia"
    : key === "usar" ? "conversar" : key;
  document.querySelectorAll(".rail a.nav").forEach((a) => {
    const here = a.getAttribute("href") === `#/${nav}` || (a.classList.contains("more") && IN_MORE.has(nav));
    if (here) a.setAttribute("aria-current", "page");
    else a.removeAttribute("aria-current");
  });
  if (typeof cleanup === "function") { try { cleanup(); } catch {} }
  cleanup = null;
  tts.stop();
  const root = $("#view");
  const mine = ++seq;
  const alive = () => mine === seq; // a tela ainda é esta? (as telas checam depois de cada espera)
  try {
    const mod = await ROUTES[key]();
    if (!alive()) return;
    // Cada tela desenha no próprio contêiner: se você sair antes de ela terminar de carregar,
    // o que ela desenhar depois cai num contêiner que já saiu da página.
    const page = h("div", { class: "page" });
    clear(root, page);
    const done = await mod.render(page, params.map(decodeURIComponent), alive);
    if (!alive()) { if (typeof done === "function") done(); return; }
    cleanup = done;
    root.focus({ preventScroll: true });
    window.scrollTo(0, 0);
  } catch (e) {
    if (alive()) clear(root, h("div", { class: "empty" }, h("p", e.message || String(e))));
  }
}

async function refreshStatus() {
  try {
    app.config = await api("/api/config");
    // Só fala quando há algo a avisar: tudo pronto não precisa de linha nenhuma.
    const c = app.config;
    const notes = [];
    if (!c.whisper_ready) notes.push("Carregando o reconhecimento de fala…");
    if (c.pron !== "pronto") notes.push(`Pronúncia: ${c.pron}.`);
    else if (c.pron_pending) notes.push(`Analisando a pronúncia de ${c.pron_pending} gravações.`);
    $("#status").textContent = notes.join(" ");
  } catch {}
}

async function start() {
  if (!token) {
    clear($("#view"), h("div", { class: "empty" },
      h("h2", "Abra pelo link do servidor"),
      h("p", "Dê dois cliques no abrir.bat (ou run.bat): ele abre o navegador no endereço certo, com o código de acesso.")));
    return;
  }
  try {
    app.config = await api("/api/config");
  } catch (e) {
    clear($("#view"), h("div", { class: "empty" }, h("h2", "O servidor não respondeu"), h("p", e.message)));
    return;
  }
  if (!app.config.pattern_pt) {
    // Página nova, servidor da versão 1 ainda ligado: ele serve estes arquivos, mas não tem as rotas novas.
    clear($("#view"), h("div", { class: "empty" },
      h("h2", "Falta reiniciar o servidor"),
      h("p", "Esta é a versão nova do app, mas a janela preta do app ainda está rodando a versão antiga. " +
             "Feche aquela janela e abra o app de novo.")));
    return;
  }
  window.addEventListener("hashchange", route);
  // Primeira vez (sem perfil ou sem Claude): a tela de boas-vindas vem antes de tudo.
  if (app.config.onboarding && !location.hash.startsWith("#/boas-vindas")) location.hash = "#/boas-vindas";
  await route();
  refreshStatus();
  setInterval(refreshStatus, 15000);
}

start();
