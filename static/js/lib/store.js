// Preferências do navegador (voz, velocidade...). Mesmo prefixo da versão 1, para não perder nada.
export function get(key, fallback) {
  const v = localStorage.getItem("ci." + key);
  return v === null ? fallback : JSON.parse(v);
}

export function set(key, value) {
  localStorage.setItem("ci." + key, JSON.stringify(value));
}
