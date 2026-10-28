// Conversa com o servidor local. O token vem no link (?t=...) e fica na URL de propósito:
// no iPhone, o ícone da tela inicial não enxerga o que o Safari guardou.
import { get, set } from "./store.js";

export let token = null;

(function readToken() {
  const url = new URL(location.href);
  const t = url.searchParams.get("t");
  if (t) set("token", t);
  token = get("token", null);
  if (!t && token) {
    url.searchParams.set("t", token);
    history.replaceState(null, "", url.pathname + url.search + url.hash);
  }
})();

export async function api(path, { body, method } = {}) {
  const headers = { "X-Token": token || "" };
  let payload = body;
  if (body && !(body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }
  let res;
  try {
    res = await fetch(path, { method: method || (body ? "POST" : "GET"), headers, body: payload });
  } catch {
    throw new Error("Sem conexão com o servidor. A janela preta do app está aberta?");
  }
  if (!res.ok) {
    let msg = `Erro ${res.status}`;
    try {
      const j = await res.json();
      if (j.detail) msg = typeof j.detail === "string" ? j.detail : msg;
    } catch {}
    throw new Error(msg);
  }
  const type = res.headers.get("content-type") || "";
  return type.includes("json") ? res.json() : res.blob();
}

export function form(fields) {
  const f = new FormData();
  for (const [k, v] of Object.entries(fields)) {
    if (v === undefined || v === null) continue;
    if (Array.isArray(v) && v[0] instanceof Blob) f.append(k, v[0], v[1]);
    else f.append(k, typeof v === "object" && !(v instanceof Blob) ? JSON.stringify(v) : v);
  }
  return f;
}

// Envia mesmo quando a aba fecha (o token vai na URL porque o sendBeacon não manda cabeçalho).
export function beacon(path, body) {
  const url = `${path}?t=${encodeURIComponent(token || "")}`;
  const blob = new Blob([JSON.stringify(body)], { type: "application/json" });
  let sent = false;
  try {
    sent = !!navigator.sendBeacon && navigator.sendBeacon(url, blob);
  } catch {
    sent = false; // alguns Chrome recusam Blob com tipo JSON no sendBeacon
  }
  if (!sent) {
    fetch(url, { method: "POST", body: blob, keepalive: true, headers: { "Content-Type": "application/json" } }).catch(() => {});
  }
}
