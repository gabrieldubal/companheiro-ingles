// Tempo de prática por atividade: conta só enquanto a aba está visível e houve ação recente.
// Manda o que juntou sempre que a aba some (no iPhone, o app pode ser fechado sem aviso).
import { beacon } from "./api.js";

const IDLE_LIMIT = 3 * 60 * 1000; // 3 minutos parado não conta

export function track(kind, ref = "") {
  let pending = 0;
  let lastAction = Date.now();
  let stopped = false;
  const bump = () => (lastAction = Date.now());
  const events = ["pointerdown", "keydown"];
  events.forEach((e) => document.addEventListener(e, bump, true));
  const timer = setInterval(() => {
    if (document.visibilityState === "visible" && Date.now() - lastAction < IDLE_LIMIT) pending += 5;
  }, 5000);
  function flush() {
    if (pending < 15) return; // o servidor ignora menos que isso
    beacon("/api/activity", { kind, ref, seconds: pending });
    pending = 0;
  }
  const onHide = () => document.visibilityState === "hidden" && flush();
  document.addEventListener("visibilitychange", onHide);
  window.addEventListener("pagehide", flush);
  return {
    bump,
    stop() {
      if (stopped) return;
      stopped = true;
      clearInterval(timer);
      events.forEach((e) => document.removeEventListener(e, bump, true));
      document.removeEventListener("visibilitychange", onHide);
      window.removeEventListener("pagehide", flush);
      flush();
    },
  };
}
