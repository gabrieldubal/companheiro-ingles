// "Mais" (só no celular): as telas que não cabem no menu de baixo.
import { h } from "../lib/dom.js";

const LINKS = [
  ["#/perguntar", "Perguntar", "Dúvidas de inglês e pedidos para o app, com os seus dados."],
  ["#/entender", "Entender", "Aulas curtas sobre os seus erros e os seus sons, com exercício."],
  ["#/erros", "Meus erros", "Pronúncia, gramática e palavras novas, com prova."],
  ["#/fale-certo", "Fale certo", "Diga do jeito certo os erros que estão na hora de revisar."],
  ["#/progresso", "Progresso", "Minutos por semana, cada som ao longo do tempo, as conversas."],
  ["#/historico", "Histórico", "Conversas e leituras feitas, com o resumo de cada uma."],
  ["#/ajustes", "Ajustes", "Meta da semana, objetivo, voz, perfil e vocabulário."],
];

export function render(root) {
  root.append(h("header", h("h1", "Mais")),
    h("div", LINKS.map(([href, title, sub]) =>
      h("a", { class: "scenario-link", href }, h("strong", title), h("span", sub)))));
}
