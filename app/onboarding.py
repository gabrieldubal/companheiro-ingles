"""Boas-vindas: o que um amigo precisa na primeira vez.

1. Ligar o app ao Claude: colar o código que recebeu (o "código do app", gerado pelo infra/chaves.py),
   que tem o endereço do intermediário e a chave pessoal. Vira o data/proxy.json.
2. Contar quem é: nome, nível, para que precisa do inglês, trabalho, interesses. Vira o perfil
   que o tutor lê (data/perfil.md), o objetivo, o nível e os nomes para o Whisper reconhecer.
3. Os cenários de conversa dele, gerados pelo Claude a partir do perfil (data/cenarios.json).
"""
import base64
import json

from . import config, db, llm, tutor

PREFIX = "CI1-"


def _profile_ok() -> bool:
    try:
        return len(config.PROFILE.read_text(encoding="utf-8").strip()) >= 20
    except OSError:
        return False


def status() -> dict:
    brain = llm.available()
    profile = _profile_ok()
    return {"needed": not (brain and profile), "brain": brain, "profile": profile,
            "backend": llm.backend_label(), "scenarios": len(tutor.custom_scenarios()), "data_dir": str(config.DATA)}


def encode(url: str, key: str) -> str:
    raw = json.dumps({"url": url, "key": key}, separators=(",", ":")).encode()
    return PREFIX + base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode(code: str) -> dict:
    """Aceita o código CI1-... ou o conteúdo de um proxy.json colado."""
    code = "".join(code.split())
    try:
        if code.startswith(PREFIX):
            b = code[len(PREFIX):]
            conf = json.loads(base64.urlsafe_b64decode(b + "=" * (-len(b) % 4)))
        else:
            conf = json.loads(code)
    except (ValueError, TypeError):
        raise ValueError("Esse código não parece certo. Copie de novo, inteiro, a partir do CI1-.")
    if not str(conf.get("url", "")).startswith("https://") or not str(conf.get("key", "")).startswith("ci_"):
        raise ValueError("Esse código não parece certo. Copie de novo, inteiro, a partir do CI1-.")
    return {"url": conf["url"], "key": conf["key"]}


def connect(code: str) -> str:
    """Grava o proxy.json e testa com um pedido curtinho. Se falhar, volta ao que era antes."""
    conf = decode(code)
    old = config.PROXY_FILE.read_text(encoding="utf-8") if config.PROXY_FILE.exists() else None
    config.PROXY_FILE.write_text(json.dumps(conf), encoding="utf-8")
    schema = {"type": "object", "properties": {"ok": {"type": "string"}}, "required": ["ok"], "additionalProperties": False}
    try:
        llm.complete_json("Reply with ok set to the word yes.", "Ping.", schema)
    except llm.LLMError:
        if old is None:
            config.PROXY_FILE.unlink(missing_ok=True)
        else:
            config.PROXY_FILE.write_text(old, encoding="utf-8")
        raise
    return llm.backend_label()


def save_profile(f: dict):
    """Escreve o perfil em português, do jeito que o tutor lê, e guarda objetivo, nível e nomes."""
    name = f.get("name", "").strip()
    lines = ["# Sobre mim", ""]
    if name:
        lines.append(f"Meu nome é {name}." + (f" Pode me chamar de {f['nickname'].strip()}." if f.get("nickname", "").strip() else ""))
    for label, key in (("Para que eu preciso do inglês", "goal"), ("O que eu faço (trabalho ou estudo)", "work"),
                       ("Do que eu gosto e sobre o que gosto de conversar", "interests"),
                       ("Um pouco da minha vida", "life"), ("O que mais me trava no inglês", "struggles")):
        value = f.get(key, "").strip()
        if value:
            lines += ["", f"## {label}", value]
    config.PROFILE.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    if f.get("goal", "").strip():
        db.set_setting("goal", f["goal"].strip()[:300])
    try:
        level = float(f.get("level") or 0)
    except (TypeError, ValueError):
        level = 0
    if 1 <= level <= 4:
        db.set_setting("level", str(level))
    names = [n.strip() for n in f.get("names", "").replace(",", "\n").splitlines() if n.strip()]
    if name:
        names = [name.split()[0]] + names
    if names:
        config.VOCAB.write_text("\n".join(dict.fromkeys(names)) + "\n", encoding="utf-8")
