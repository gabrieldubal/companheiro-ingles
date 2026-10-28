// Ajustes: a sua semana e o objetivo, a voz, o perfil que o tutor lê e o vocabulário do Whisper.
import { api } from "../lib/api.js";
import { h, toast } from "../lib/dom.js";
import { get, set } from "../lib/store.js";
import * as tts from "../lib/tts.js";

function localCheck(key, fallback, label) {
  const input = h("input", { type: "checkbox" });
  input.checked = get(key, fallback);
  input.onchange = () => set(key, input.checked);
  return h("label", { class: "check" }, input, label);
}

// O código do app (de quem te passou o app): troca a chave do intermediário sem reinstalar nada.
function connection(s) {
  const code = h("textarea", { rows: 2, placeholder: "CI1-..." });
  const btn = h("button", { class: "btn small secondary", type: "button" }, "Trocar o código");
  const state = h("p", { class: "soft small" }, `Agora: ${s.backend}.`);
  btn.onclick = async () => {
    if (!code.value.trim()) return;
    btn.disabled = true;
    btn.textContent = "Testando…";
    try {
      const r = await api("/api/onboarding/codigo", { body: { code: code.value } });
      state.textContent = `Agora: ${r.backend}.`;
      code.value = "";
      toast("Código trocado e testado.");
    } catch (e) {
      toast(e.message);
    } finally {
      btn.disabled = false;
      btn.textContent = "Trocar o código";
    }
  };
  return h("section", { class: "section" }, h("h2", "Conexão com o Claude"), state,
    h("p", { class: "soft small", style: { margin: "6px 0 10px" } },
      "Se quem te passou o app mandar um código novo (começa com CI1-), cole aqui. O app testa antes de trocar."),
    h("label", { class: "field" }, code), btn);
}

export async function render(root) {
  const s = await api("/api/settings");

  const weekly = h("select", [1, 2, 3, 4, 5, 6, 7].map((n) => h("option", { value: n, selected: String(n) === s.weekly_target },
    `${n} ${n === 1 ? "sessão" : "sessões"} por semana`)));
  const minutes = h("select", [10, 15, 20, 30].map((n) => h("option", { value: n, selected: String(n) === s.session_minutes }, `${n} minutos`)));
  const perDay = h("select", [0, 5, 10, 15, 20, 30].map((n) => h("option", { value: n, selected: String(n) === s.cards_per_day },
    n ? `${n} cartões novos por dia` : "Nenhum cartão novo (só revisões)")));
  const goal = h("input", { type: "text", value: s.goal, placeholder: "Ex.: fazer a entrevista técnica em inglês até março" });
  const profile = h("textarea", { rows: 14 });
  profile.value = s.profile;
  const vocab = h("textarea", { rows: 10 });
  vocab.value = s.vocab;

  const voices = tts.listVoices();
  const voice = h("select", voices.length
    ? voices.map((v) => h("option", { value: v.voiceURI, selected: v.voiceURI === get("voice", "") }, `${v.name} (${v.lang})`))
    : [h("option", "Voz padrão do navegador")]);
  voice.onchange = () => { set("voice", voice.value); tts.speak("Hi! This is my voice."); };
  const rateLabel = h("b");
  const rate = h("input", { type: "range", min: "0.6", max: "1.2", step: "0.05", value: get("rate", 0.9) });
  const showRate = () => (rateLabel.textContent = `${Number(rate.value).toFixed(2)}x`);
  showRate();
  rate.oninput = () => { set("rate", Number(rate.value)); showRate(); };
  rate.onchange = () => tts.speak("This is how fast I will speak.");

  async function save(btn) {
    btn.disabled = true;
    try {
      await api("/api/settings", { method: "PUT", body: {
        weekly_target: parseInt(weekly.value, 10), session_minutes: parseInt(minutes.value, 10),
        cards_per_day: parseInt(perDay.value, 10),
        goal: goal.value, profile: profile.value, vocab: vocab.value,
      } });
      toast("Ajustes salvos.");
    } catch (e) {
      toast(e.message);
    } finally {
      btn.disabled = false;
    }
  }
  const saveBtn = h("button", { class: "btn", type: "button" }, "Salvar ajustes");
  saveBtn.onclick = () => save(saveBtn);

  // Duas colunas: o ritmo e a voz à esquerda, o que o tutor e o Whisper leem à direita.
  root.append(
    h("header", h("h1", "Ajustes")),
    h("div", { class: "split" }, h("div",
    h("section", h("h2", "Sua semana"),
      h("p", { class: "soft", style: { margin: "6px 0 16px" } }, "A meta é por semana: perder um dia não zera nada."),
      h("label", { class: "field" }, h("span", "Sessões por semana"), weekly),
      h("label", { class: "field" }, h("span", "Duração de uma sessão"), minutes),
      h("label", { class: "field" }, h("span", "Seu objetivo com o inglês"), goal),
      h("label", { class: "field" }, h("span", "Cartões novos por dia (as revisões não têm limite)"), perDay)),
    h("section", { class: "section" }, h("h2", "Voz e microfone"),
      h("p", { class: "soft", style: { margin: "6px 0 16px" } }, "Estes ficam guardados neste navegador."),
      h("label", { class: "field" }, h("span", "Voz do tutor"), voice),
      h("label", { class: "field" }, h("span", h("span", "Velocidade da fala: "), rateLabel), rate),
      localCheck("autoSpeak", true, "Ler as respostas do tutor em voz alta"),
      localCheck("review", false, "Revisar a transcrição antes de enviar"),
      localCheck("saveAudio", true, "Guardar os áudios das conversas neste computador (o detector de pronúncia precisa deles)"))),
    h("div",
    h("section", h("h2", "Perfil"),
      h("p", { class: "soft", style: { margin: "6px 0 16px" } }, "O tutor lê isto no começo de cada conversa para falar do seu mundo."),
      h("label", { class: "field" }, profile)),
    h("section", { class: "section" }, h("h2", "Vocabulário do Whisper"),
      h("p", { class: "soft", style: { margin: "6px 0 16px" } }, "Nomes e termos seus, um por linha, para o Whisper reconhecer. Até uns 40."),
      h("label", { class: "field" }, vocab)))),
    h("div", { class: "row" }, saveBtn),
    h("div", { class: "split section" }, connection(s),
    h("section", { class: "section" }, h("h2", "Sistema"),
      h("ul", { class: "list", style: { marginTop: "12px" } },
        h("li", `Versão: ${s.version}`),
        h("li", `Cérebro: ${s.backend}`), h("li", `Ouvido: Whisper ${s.whisper}`), h("li", `Pronúncia: ${s.pron}`),
        h("li", "Seus dados (banco, áudios, cartões, backups) ficam em: ", h("code", s.data_dir))))));
}
