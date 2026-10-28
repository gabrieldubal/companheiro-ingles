// Tema: claro, escuro ou o do sistema. O index.html aplica a escolha antes de pintar (sem piscar);
// aqui ficam a troca (menu e Ajustes) e o acompanhamento do sistema quando a escolha é "auto".
import { get, set } from "./store.js";

const media = matchMedia("(prefers-color-scheme: dark)");

export const choice = () => get("theme", "auto");
export const current = () => document.documentElement.dataset.theme;

export function apply(c = choice()) {
  const dark = c === "dark" || (c === "auto" && media.matches);
  document.documentElement.dataset.theme = dark ? "dark" : "light";
  document.querySelector('meta[name="theme-color"]')?.setAttribute("content", dark ? "#121A22" : "#1F6B4F");
  window.dispatchEvent(new CustomEvent("themechange"));
}

export function choose(c) {
  set("theme", c);
  apply(c);
}

/** O botão do menu: troca para o outro tema (e passa a valer a escolha, não mais o sistema). */
export function toggle() {
  choose(current() === "dark" ? "light" : "dark");
}

media.addEventListener("change", () => { if (choice() === "auto") apply(); });
