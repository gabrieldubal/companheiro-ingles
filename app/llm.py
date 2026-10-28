"""Chamada ao Claude com resposta em JSON, por dois caminhos: Claude Code (CLI) ou API."""
import json
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

from . import config


class LLMError(Exception):
    pass


def complete_json(system: str, prompt: str, schema: dict) -> dict:
    t0 = time.time()
    backend = config.llm_backend()
    if backend == "api":
        data = _api(system, prompt, schema)
    elif backend == "demo":
        data = _demo(schema)
    elif backend == "proxy":
        data = _proxy(system, prompt, schema)
    else:
        data = _cli(system, prompt, schema)
    print(f"[llm] {backend} {time.time() - t0:.1f}s")
    return data


def available() -> bool:
    """Há um jeito de falar com o Claude? (Sem isso, a tela de boas-vindas pede o código do app.)"""
    backend = config.llm_backend()
    if backend in ("demo", "api"):
        return True
    if backend == "proxy":
        try:
            _proxy_conf()
            return True
        except LLMError:
            return False
    try:
        _claude_exe()
        return True
    except LLMError:
        return False


def backend_label() -> str:
    backend = config.llm_backend()
    if backend == "demo":
        return "demo (respostas prontas, sem Claude)"
    if backend == "proxy":
        try:
            host = urlparse(_proxy_conf()["url"]).hostname or "?"
        except LLMError as e:
            return f"intermediário: {e}"
        return f"Claude pelo intermediário ({host.split('.')[0][:12]}…), esforço {config.LLM_EFFORT}"
    model = config.LLM_MODEL or ("opus" if backend == "cli" else "claude-opus-5-5")
    name = {"cli": "Claude Code desta máquina", "api": "API da Anthropic"}.get(backend, backend)
    return f"{name} (modelo {model}, esforço {config.LLM_EFFORT})"


# --- Demo: respostas prontas para testar a interface sem gastar token ---------

def _demo(schema: dict) -> dict:
    time.sleep(1)
    if "meanings" in schema["properties"]:
        return {"meanings": []}
    if "scenarios" in schema["properties"]:
        return {"scenarios": [
            {"title": "Reunião sobre o seu projeto", "subtitle": "Demonstração",
             "role": "You are Pat, a project manager who asks the student about their current project."},
            {"title": "Uma viagem que você quer fazer", "subtitle": "Demonstração",
             "role": "You are Lee, a travel agent helping the student plan a trip they want to take."}]}
    if "passages" in schema["properties"]:
        return {"passages": [{"title": "Um dia de trabalho", "sentences": [
            "I think three things matter in a good model.", "First, the data has to be clean.",
            "Then I check the results with my team."]}]}
    if "prompts" in schema["properties"]:
        return {"prompts": [{"id": 0, "question_en": "What did you do on the last day of your trip to Peru?",
                             "question_pt": "O que você fez no último dia da sua viagem ao Peru?",
                             "target": "past simple: visited, went, saw"}]}
    if "used_target" in schema["properties"]:
        return {"used_target": True, "target_ok": False,
                "verdict_pt": "Demonstração: o passado apareceu, mas o 'in the last day' voltou.",
                "better": "On the last day, we visited Machu Picchu and it was amazing.",
                "corrections": [{"original": "in the last day", "better": "on the last day", "pattern":
                                 "prepositions of time and place (in/on/at)", "explanation_pt": "Com dia, a preposição é on.",
                                 "meaning_pt": "no último dia"}],
                "pattern_counts": [{"pattern": "prepositions of time and place (in/on/at)", "count": 1,
                                    "original": "in the last day", "better": "on the last day", "meaning_pt": "no último dia"}]}
    if "rule_pt" in schema["properties"]:
        return {"title": "Aula de demonstração", "rule_pt": "Regra de demonstração em duas frases. Use on com dias.",
                "why_pt": "Em português é 'no' para tudo.",
                "examples": [{"en": "On Monday I have a meeting.", "pt": "Na segunda tenho reunião."}],
                "exercise": [{"prompt": "___ the final day, we visited Machu Picchu.", "options": ["In", "On", "At"],
                              "answer": 1, "explain_pt": "Dia pede on."}],
                "cards": [{"front": "____ the final day (no último dia)", "back": "on the final day"}]}
    if "actions" in schema["properties"]:
        empty = dict.fromkeys(["front", "back", "note", "word", "meaning_pt", "example", "tag", "text", "value"], "")
        return {
            "reply": "Resposta de demonstração. Com *the company*, o verbo leva **-s**: *the company uses*. "
                     "Você disse *the company use* duas vezes na última conversa.\n\n- *My team uses Python.*\n"
                     "- *The model needs more data.*",
            "actions": [
                {**empty, "type": "criar_cartao", "front": "Como se diz: a empresa usa satélites",
                 "back": "The company uses satellites.", "note": "Terceira pessoa: o verbo leva -s."},
                {**empty, "type": "frase_treino", "tag": "th-voiceless", "text": "I think three months of data is enough."},
                {**empty, "type": "abrir", "value": "#/cartoes", "text": "Revisar os cartões"},
            ],
        }
    if "items" in schema["properties"]:
        return {"items": [{"text": "I think three thousand trees grow on the farm.", "targets": ["think", "three", "thousand"]}]}
    if "summary_pt" in schema["properties"]:
        return {
            "summary_pt": "Resumo de demonstração: a conversa fluiu e os erros não atrapalharam o sentido.",
            "went_well_pt": ["Respondeu direto ao que foi perguntado."],
            "focus_pt": "Treinar o passado: 'I went', 'I had', 'I chose'.",
            "best_sentences": ["I chose Mask R-CNN because it gives the area of each panel."],
            "cefr_estimate": "B1", "scale_estimate": 2.5,
            "level_comment_pt": "Estimativa de demonstração.",
        }
    return {
        "reply": "That sounds interesting! What did you do after that?",
        "reply_pt": "Que interessante! O que você fez depois disso?",
        "corrections": [{
            "original": "I go to the office yesterday", "better": "I went to the office yesterday",
            "explanation_pt": "Ação terminada no passado pede o past simple: go vira went.",
            "pattern": "past simple (finished actions)", "meaning_pt": "eu fui ao escritório ontem",
        }],
        "new_words": [{"word": "commute", "meaning_pt": "trajeto até o trabalho",
                       "example": "My commute takes forty minutes."}],
        "pattern_counts": [
            {"pattern": "past simple (finished actions)", "count": 2,
             "original": "I go to the office yesterday", "better": "I went to the office yesterday"},
            {"pattern": "third person -s", "count": 3, "original": "the company use", "better": "the company uses"},
        ],
        "good_uses": [],
    }


# --- Intermediário (o app dos amigos) ------------------------------------------------
# A chave pessoal fica em data/proxy.json: {"url": "...", "key": "ci_..."}. As credenciais do
# Bedrock ficam só no intermediário; esta chave abre apenas ele, com um limite por mês.

def _proxy_conf() -> dict:
    try:
        conf = json.loads(config.PROXY_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise LLMError("Falta o data/proxy.json com o endereço e a chave do app.")
    if not conf.get("url") or not conf.get("key"):
        raise LLMError("O data/proxy.json precisa de url e key.")
    return conf


def _proxy(system: str, prompt: str, schema: dict) -> dict:
    conf = _proxy_conf()
    body = json.dumps({"system": system, "prompt": prompt, "schema": schema, "effort": config.LLM_EFFORT}).encode()
    req = urllib.request.Request(conf["url"], data=body, method="POST", headers={
        "content-type": "application/json", "authorization": f"Bearer {conf['key']}"})
    try:
        with urllib.request.urlopen(req, timeout=150) as r:
            out = json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read()).get("error", "")
        except ValueError:
            msg = ""
        if e.code == 401:
            raise LLMError(msg or "A chave do app não vale mais. Fale com quem te passou o app.")
        if e.code == 402:
            raise LLMError(msg or "O limite deste mês acabou.")
        if e.code == 429:
            raise LLMError("Muitos pedidos agora. Tente de novo em instantes.")
        raise LLMError(msg or f"O intermediário respondeu {e.code}.")
    except (urllib.error.URLError, TimeoutError):
        raise LLMError("Sem conexão com o intermediário. Confira a internet.")
    except ValueError:
        raise LLMError("Resposta inesperada do intermediário.")
    if "data" not in out:
        raise LLMError(out.get("error") or "Resposta inesperada do intermediário.")
    return out["data"]


# --- Claude Code (CLI) -------------------------------------------------------

_CLI_CWD = config.DATA / "cli-cwd"  # pasta vazia: o CLI não carrega nada do projeto


def _claude_exe() -> str:
    exe = shutil.which("claude")
    if exe:
        return exe
    fallback = Path.home() / ".local" / "bin" / "claude.exe"
    if fallback.exists():
        return str(fallback)
    raise LLMError("Não achei o Claude Code (comando 'claude') nesta máquina.")


def _cli(system: str, prompt: str, schema: dict) -> dict:
    _CLI_CWD.mkdir(exist_ok=True)
    cmd = [
        _claude_exe(), "-p",
        "--output-format", "json",
        "--tools", "",
        "--strict-mcp-config",
        # "user" carrega o ~/.claude/settings.json, onde fica a configuração do Bedrock
        "--setting-sources", "user",
        "--no-session-persistence",
        "--model", config.LLM_MODEL or "opus",
        "--effort", config.LLM_EFFORT,
        "--system-prompt", system,
        "--json-schema", json.dumps(schema),
    ]
    try:
        proc = subprocess.run(
            cmd, input=prompt, capture_output=True, text=True,
            encoding="utf-8", timeout=180, cwd=_CLI_CWD,
        )
    except subprocess.TimeoutExpired:
        raise LLMError("O Claude demorou demais para responder.")
    try:
        out = json.loads(proc.stdout)
    except json.JSONDecodeError:
        detail = (proc.stderr or proc.stdout).strip()[:300]
        raise LLMError(f"Resposta inesperada do Claude Code: {detail}")
    if out.get("is_error"):
        raise LLMError(f"Erro do Claude Code: {str(out.get('result'))[:300]}")
    data = out.get("structured_output")
    if data is None:
        try:
            data = json.loads(out.get("result") or "")
        except json.JSONDecodeError:
            raise LLMError("O Claude não devolveu JSON válido.")
    return data


# --- API da Anthropic --------------------------------------------------------

_client = None


def _api(system: str, prompt: str, schema: dict) -> dict:
    import anthropic

    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    try:
        resp = _client.beta.messages.create(
            model=config.LLM_MODEL or "claude-opus-5-5",
            max_tokens=8000,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": prompt}],
            output_config={
                "effort": config.LLM_EFFORT,
                "format": {"type": "json_schema", "schema": schema},
            },
            # Se o modelo recusar, o servidor tenta de novo com outro modelo.
            betas=["server-side-fallback-2026-07-01"],
            extra_body={"fallbacks": "default"},
        )
    except anthropic.RateLimitError:
        raise LLMError("Limite de uso da API atingido. Tente de novo em instantes.")
    except anthropic.APIStatusError as e:
        raise LLMError(f"Erro da API ({e.status_code}): {e.message[:200]}")
    except anthropic.APIConnectionError:
        raise LLMError("Sem conexão com a API da Anthropic.")
    if resp.stop_reason == "refusal":
        raise LLMError("O modelo recusou esta resposta. Tente reformular.")
    text = next((b.text for b in resp.content if b.type == "text"), "")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        raise LLMError("A API não devolveu JSON válido.")
