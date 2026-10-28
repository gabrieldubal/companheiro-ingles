// Boas-vindas: a primeira vez de cada pessoa. Ligar ao Claude (o código do app), contar quem é
// (vira o perfil que o tutor lê) e criar os cenários de conversa dela. Passos já feitos são pulados.
import { api } from "../lib/api.js";
import { clear, h, toast } from "../lib/dom.js";
import { app } from "../main.js";

const STEPS = ["Ligar ao Claude", "Sobre você", "Os seus cenários", "Pronto"];

export async function render(root, _params, alive) {
  let st = await api("/api/onboarding");
  if (!alive()) return;
  let step = !st.brain ? 0 : !st.profile ? 1 : st.scenarios ? 3 : 2;
  const steps = h("ol", { class: "ladder", "aria-label": "Passos" });
  const stage = h("section", { class: "stage", style: { marginTop: "22px" } });
  const mark = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  mark.setAttribute("class", "brand-mark");
  mark.setAttribute("aria-hidden", "true");
  mark.innerHTML = '<use href="#i-marca"/>'; // só a referência ao símbolo do index.html
  root.append(h("header", mark,
    h("h1", "Boas-vindas ao Companheiro de inglês"),
    h("p", "Um laboratório de fala só seu: conversa por voz, pronúncia som a som, cartões de revisão e aulas com os seus " +
           "próprios erros. Tudo fica neste computador. Antes de começar, três passos rápidos."),
    steps), stage);

  function draw() {
    clear(steps, STEPS.map((t, i) => h("li", { class: i < step ? "done" : i === step ? "cur" : "" }, t)));
    [connect, profile, scenarios, done][step]();
  }

  async function refreshConfig() {
    try { app.config = await api("/api/config"); } catch {}
  }

  function connect() {
    const code = h("textarea", { rows: 3, placeholder: "CI1-…", "aria-label": "Código do app" });
    const btn = h("button", { class: "btn", type: "button" }, "Conectar");
    btn.onclick = async () => {
      if (!code.value.trim()) { toast("Cole o código que você recebeu."); return; }
      btn.disabled = true;
      btn.textContent = "Testando a conexão…";
      try {
        st = await api("/api/onboarding/codigo", { body: { code: code.value } });
        if (!alive()) return;
        step = st.profile ? (st.scenarios ? 3 : 2) : 1;
        draw();
      } catch (e) {
        toast(e.message);
        btn.disabled = false;
        btn.textContent = "Conectar";
      }
    };
    clear(stage, h("h2", "Ligar ao Claude"),
      h("p", { class: "soft", style: { margin: "8px 0 14px" } },
        "Quem te passou o app mandou um código que começa com CI1-. Cole aqui. Ele liga o app ao Claude, com um limite " +
        "de uso por mês; não precisa de conta nem de senha."),
      h("label", { class: "field" }, code), btn);
    code.focus();
  }

  function profile() {
    const f = {};
    const field = (key, label, { area = false, ph = "", hint = "" } = {}) => {
      f[key] = h(area ? "textarea" : "input", area ? { rows: 3, placeholder: ph } : { type: "text", placeholder: ph });
      return h("label", { class: "field" }, h("span", label), f[key], hint ? h("small", { class: "muted" }, hint) : null);
    };
    const level = h("select", (app.config.levels || []).map((l) =>
      h("option", { value: l.value, selected: l.value === app.config.default_level }, l.label)));
    const btn = h("button", { class: "btn", type: "button" }, "Salvar e continuar");
    btn.onclick = async () => {
      btn.disabled = true;
      try {
        const body = Object.fromEntries(Object.entries(f).map(([k, el]) => [k, el.value]));
        st = await api("/api/onboarding/perfil", { body: { ...body, level: parseFloat(level.value) } });
        if (!alive()) return;
        await refreshConfig();
        step = 2;
        draw();
      } catch (e) {
        toast(e.message);
        btn.disabled = false;
      }
    };
    clear(stage, h("h2", "Sobre você"),
      h("p", { class: "soft", style: { margin: "8px 0 16px" } },
        "O tutor lê isto antes de cada conversa, para falar do seu mundo e não de assuntos genéricos. Escreva do seu " +
        "jeito, em português. Dá para mudar depois em Ajustes."),
      h("div", { class: "form-grid" },
        field("name", "Seu nome"), field("nickname", "Como prefere ser chamado (opcional)")),
      h("label", { class: "field" }, h("span", "Como está o seu inglês falado hoje"), level),
      field("goal", "Para que você precisa do inglês", { area: true, ph: "Ex.: entrevistas para vagas remotas; uma viagem em julho; reuniões com o time de fora" }),
      field("work", "O que você faz: trabalho ou estudo", { area: true, ph: "Ex.: sou enfermeira num hospital; estudo engenharia e faço estágio numa fábrica" }),
      field("interests", "Do que você gosta de falar", { area: true, ph: "Ex.: futebol, séries, cozinhar, trilhas, tecnologia" }),
      field("life", "Um pouco da sua vida (opcional)", { area: true, ph: "Onde mora, com quem, planos, viagens que fez ou quer fazer" }),
      field("struggles", "O que mais te trava no inglês (opcional)", { area: true, ph: "Ex.: entendo, mas travo para responder; tenho vergonha do sotaque" }),
      field("names", "Nomes que você fala e o reconhecimento de voz pode errar (opcional)",
        { ph: "Ex.: o nome da sua empresa, cidade, pessoas", hint: "Separados por vírgula." }),
      btn);
    f.name.focus();
  }

  function scenarios() {
    const btn = h("button", { class: "btn", type: "button" }, "Criar os meus cenários");
    const skip = h("button", { class: "btn quiet", type: "button" }, "Pular por agora");
    const out = h("div");
    btn.onclick = async () => {
      btn.disabled = true;
      skip.disabled = true;
      btn.textContent = "Criando com o Claude… (uns 15 segundos)";
      try {
        const r = await api("/api/onboarding/cenarios", { body: {} });
        if (!alive()) return;
        await refreshConfig();
        clear(out, h("ul", { class: "list", style: { marginTop: "14px" } }, r.created.map((s) =>
          h("li", h("p", h("b", s.title)), h("p", { class: "small soft" }, s.subtitle)))),
          h("div", { class: "row", style: { marginTop: "14px" } },
            h("button", { class: "btn", type: "button", onclick: () => { step = 3; draw(); } }, "Continuar")));
        btn.hidden = true;
        skip.hidden = true;
      } catch (e) {
        toast(e.message);
        btn.disabled = false;
        skip.disabled = false;
        btn.textContent = "Criar os meus cenários";
      }
    };
    skip.onclick = () => { step = 3; draw(); };
    clear(stage, h("h2", "Os seus cenários"),
      h("p", { class: "soft", style: { margin: "8px 0 16px" } },
        "Além das conversas de sempre (do dia a dia, viagem, trabalho, entrevista), o Claude cria quatro feitas para " +
        "você, a partir do que você contou: o seu objetivo, o seu trabalho, os seus assuntos."),
      h("div", { class: "row" }, btn, skip), out);
  }

  function done() {
    app.config.onboarding = false;
    clear(stage, h("h2", "Tudo pronto"),
      h("p", { style: { margin: "8px 0 6px" } },
        "Comece pela leitura em voz alta: são 24 frases curtas, uns 10 minutos, e com elas o app descobre quais sons " +
        "você mais precisa treinar. Depois disso, a tela Hoje monta a sua sessão de cada dia."),
      h("ul", { class: "tips" },
        h("li", "Use no Microsoft Edge: ele tem as vozes mais naturais para ouvir o nativo."),
        h("li", "Fone ajuda, mas não é obrigatório. Num lugar onde não dá para falar, use \"Não posso falar\" na tela Hoje."),
        h("li", "Os seus dados ficam só neste computador, em: ", h("code", st.data_dir))),
      h("div", { class: "row section", style: { marginTop: "18px" } },
        h("a", { class: "btn", href: "#/leitura" }, "Fazer a leitura em voz alta"),
        h("a", { class: "btn secondary", href: "#/hoje" }, "Ir para Hoje")));
  }

  draw();
}
