// Entender: aulas curtas sobre os seus erros, os seus sons e temas que o seu objetivo pede.
// Cada aula é feita uma vez com os seus dados e fica guardada; o exercício é corrigido na hora.
import { track } from "../lib/activity.js";
import { api } from "../lib/api.js";
import { clear, dayMonth, h, toast } from "../lib/dom.js";
import * as tts from "../lib/tts.js";

const GROUPS = [["padrao", "Os seus erros de gramática"], ["som", "Os seus sons"], ["tema", "Temas para entrevistas e calls"]];

export async function render(root, [key], alive) {
  if (!key) return renderTrilha(root, alive);
  return renderLesson(root, key, alive);
}

const href = (key) => `#/entender/${encodeURIComponent(key)}`;

async function renderTrilha(root, alive) {
  const d = await api("/api/entender");
  if (!alive()) return;
  root.append(h("header", h("h1", "Entender"),
    h("p", "Aulas curtas, feitas com os seus dados: a regra em poucas frases, por que o português engana, os seus exemplos, " +
           "um exercício corrigido na hora e cartões para levar. Dá para fazer em silêncio. Toda aula aberta fica guardada: " +
           "\"Rever\" abre do jeito que estava, sem gastar nada.")));
  const groups = h("div", { class: "groups" });
  root.append(groups);
  for (const [kind, title] of GROUPS) {
    const items = d.items.filter((t) => t.kind === kind);
    if (!items.length) continue;
    groups.append(h("section", { class: "section" }, h("h2", title),
      h("ul", { class: "list", style: { marginTop: "10px" } }, items.map((t) => h("li", { class: "row", style: { justifyContent: "space-between" } },
        h("div", h("p", h("b", t.title)), h("p", { class: "small muted" }, t.why +
          (t.score != null ? `. Feita em ${dayMonth(t.done_at)}: ${t.score} de ${t.total} no exercício.`
            : t.ready ? ". Aula pronta, exercício por fazer." : "."))),
        h("a", { class: `btn small${t.score == null ? "" : " secondary"}`, href: href(t.key) }, t.score == null ? "Estudar" : "Rever"))))));
  }
}

async function renderLesson(root, key, alive) {
  const box = h("div", h("p", { class: "soft" }, "Montando a aula com os seus dados… Na primeira vez leva uns 20 segundos."));
  root.append(h("header", h("p", { class: "date-line" }, h("a", { href: "#/entender" }, "Entender"), " / aula")), box);
  let L;
  try {
    L = await api(`/api/entender/aula?key=${encodeURIComponent(key)}`);
  } catch (e) {
    clear(box, h("p", { class: "empty" }, e.message));
    return;
  }
  if (!alive()) return;
  const tracker = track("entender", key.slice(0, 60));
  draw();

  function draw() {
    const answers = new Array(L.exercise.length).fill(null);
    const score = h("p", { class: "score" });
    const exercise = h("ol", { class: "exercise" }, L.exercise.map((q, qi) => {
      const explain = h("p", { class: "small soft", hidden: true }, q.explain_pt);
      const opts = h("div", { class: "row options" });
      q.options.forEach((o, oi) => {
        const b = h("button", { class: "opt", type: "button" }, o);
        b.onclick = () => {
          if (answers[qi] != null) return;
          answers[qi] = oi === q.answer;
          tracker.bump();
          [...opts.children].forEach((x, xi) => {
            x.disabled = true;
            if (xi === q.answer) x.classList.add("right");
            else if (xi === oi) x.classList.add("wrong");
          });
          explain.hidden = false;
          if (answers.every((a) => a != null)) finish();
        };
        opts.append(b);
      });
      return h("li", h("p", { class: "serif q" }, q.prompt), opts, explain);
    }));

    // A nota vai sozinha quando você responde a última pergunta; a tela diz que foi (ou que falhou).
    async function finish() {
      const ok = answers.filter(Boolean).length;
      score.textContent = `${ok} de ${answers.length} certas.` + (ok === answers.length ? " Agora use isso falando." : " Releia a regra e os exemplos.");
      try {
        await api("/api/entender/nota", { body: { key: L.key, score: ok, total: answers.length } });
        if (alive()) score.append(h("span", { class: "saved" }, " ✓ Salvo: a aula fica como feita em Entender e entra no Progresso."));
      } catch (e) {
        toast(`A nota da aula não foi salva: ${e.message}`);
      }
    }

    const nCards = L.cards?.length || 0;
    const cardsBtn = h("button", { class: "btn secondary small", type: "button" },
      `Levar ${nCards === 1 ? "o cartão" : `os ${nCards} cartões`} desta aula para a revisão`);
    cardsBtn.onclick = async () => {
      cardsBtn.disabled = true;
      try {
        const r = await api("/api/entender/cartoes", { body: { key: L.key } });
        toast(`${r.created} ${r.created === 1 ? "cartão entrou" : "cartões entraram"} no baralho.`);
        cardsBtn.textContent = "Cartões levados";
      } catch (e) { toast(e.message); cardsBtn.disabled = false; }
    };
    const redo = h("button", { class: "btn quiet small", type: "button" }, "Refazer a aula");
    redo.onclick = async () => {
      redo.disabled = true;
      redo.textContent = "Refazendo…";
      try {
        L = await api(`/api/entender/aula?key=${encodeURIComponent(key)}&refazer=true`);
        if (alive()) draw();
      } catch (e) { toast(e.message); redo.disabled = false; redo.textContent = "Refazer a aula"; }
    };

    const practice = L.kind === "padrao"
      ? [h("a", { class: "btn", href: `#/usar/padrao/${encodeURIComponent(L.ref)}` }, "Usar falando"),
         h("a", { class: "btn secondary", href: "#/fale-certo" }, "Fale certo")]
      : L.kind === "som"
        ? [h("a", { class: "btn", href: `#/treino/${L.ref}` }, "Treinar o som"), h("a", { class: "btn secondary", href: "#/imitar" }, "Imitar"),
           h("a", { class: "btn secondary", href: `#/usar/som/${L.ref}` }, "Usar falando")]
        : [h("a", { class: "btn", href: "#/usar" }, "Usar falando"), h("a", { class: "btn secondary", href: "#/imitar" }, "Imitar")];

    // A explicação à esquerda; o exercício e o que fazer depois, ao lado (no celular, embaixo).
    clear(box, h("h1", L.title), h("div", { class: "bench", style: { marginTop: "6px" } }, h("div", { class: "bench-main" },
      h("p", { class: "rule" }, L.rule_pt),
      L.why_pt ? h("div", { class: "tip" }, h("p", h("b", "Por que o português engana. "), L.why_pt)) : null,
      L.yours?.length ? h("section", { class: "section" }, h("h2", L.kind === "som" ? "As suas palavras" : "Os seus exemplos"),
        h("ul", { class: "list", style: { marginTop: "8px" } }, L.yours.map((y) => h("li",
          L.kind === "som"
            ? h("p", h("b", { class: "serif" }, y.wrong), h("span", { class: "small soft" }, `  ${y.note}`))
            : h("p", { class: "line serif" }, h("del", y.wrong), "  ", h("ins", y.right)),
          L.kind !== "som" && y.note ? h("p", { class: "small soft" }, y.note) : null)))) : null,
      L.examples?.length ? h("section", { class: "section" }, h("h2", "Exemplos"),
        h("ul", { class: "list", style: { marginTop: "8px" } }, L.examples.map((e) => h("li", { class: "row", style: { justifyContent: "space-between" } },
          h("div", h("p", { class: "serif", style: { fontSize: "1.15rem" } }, e.en), h("p", { class: "small soft" }, e.pt)),
          h("button", { class: "play", type: "button", onclick: () => tts.speak(e.en, 0.9) }, "▶"))))) : null),
      h("aside", { class: "bench-side" },
        L.exercise?.length ? h("section", { class: "side-block" }, h("h2", "Exercício"),
          h("p", { class: "small muted", style: { marginTop: "4px" } }, "Não precisa salvar: a nota vai sozinha quando você responde a última."),
          exercise, score) : null,
        h("div", { class: "side-block" }, h("h3", "Depois"), h("div", { class: "row", style: { marginTop: "8px" } }, practice),
          h("div", { class: "row", style: { marginTop: "10px" } }, L.cards?.length ? cardsBtn : null, redo)))));
    if (L.score != null) score.textContent = `Da última vez: ${L.score} de ${L.total}.`;
  }

  return () => tracker.stop();
}
