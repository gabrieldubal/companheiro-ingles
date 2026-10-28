"""Caminhos e ajustes. Tudo pode ser trocado por variável de ambiente."""
import os
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# COMPANHEIRO_DATA permite testar com outra pasta sem mexer no seu histórico.
DATA = Path(os.environ.get("COMPANHEIRO_DATA", ROOT / "data"))
STATIC = ROOT / "static"
# O número da versão (o empacotar.bat sobe ele a cada lançamento; as mudanças ficam no CHANGELOG.md).
_VERSION_FILE = ROOT / "VERSION"
VERSION = _VERSION_FILE.read_text(encoding="utf-8").strip() if _VERSION_FILE.exists() else "sem número"
AUDIO = DATA / "audio"  # gravações guardadas (só se você ligar a opção no app)
DATA.mkdir(parents=True, exist_ok=True)
# Tudo que é de uma pessoa fica na pasta de dados dela, e não junto do código: assim o mesmo
# código serve para qualquer um, e o pacote dos amigos não leva nada seu.
PROFILE = DATA / "perfil.md"
VOCAB = DATA / "vocabulario.txt"  # nomes e termos da pessoa, para o Whisper reconhecer
SCENARIOS_FILE = DATA / "cenarios.json"  # cenários de conversa da pessoa
for _new, _old in ((PROFILE, ROOT / "perfil.md"), (VOCAB, ROOT / "vocabulario.txt")):
    if not _new.exists() and _old.exists():  # quem instalou antes: o perfil antigo vem junto
        shutil.copy2(_old, _new)

# Abaixo desta confiança do Whisper, a palavra aparece como "pronúncia a conferir".
UNSURE_PROB = float(os.environ.get("COMPANHEIRO_UNSURE", "0.5"))

PORT = int(os.environ.get("COMPANHEIRO_PORT", "8443"))  # modo celular
PC_PORT = int(os.environ.get("COMPANHEIRO_PC_PORT", "8790"))  # modo PC (a 8000 é do Docker e a 8765 é de outro projeto aqui)

# Modelo do Whisper: tiny.en, base.en, small.en (padrão) ou medium.en.
# Maior = entende melhor o sotaque, mas demora mais na CPU.
WHISPER_MODEL = os.environ.get("COMPANHEIRO_WHISPER", "small.en")

# "cli" usa o Claude Code instalado nesta máquina (e o login dele).
# "api" usa a API da Anthropic com ANTHROPIC_API_KEY (cobrança separada).
# "proxy" usa o intermediário (infra/): o app dos amigos, com a chave pessoal em data/proxy.json.
PROXY_FILE = DATA / "proxy.json"
FORCED_LLM = os.environ.get("COMPANHEIRO_LLM", "")  # "demo" também vem daqui (run.bat --demo)


def llm_backend() -> str:
    """Decidido a cada pedido: a tela de boas-vindas grava o proxy.json com o app ligado."""
    if FORCED_LLM:
        return FORCED_LLM
    if PROXY_FILE.exists():
        return "proxy"
    return "api" if os.environ.get("ANTHROPIC_API_KEY") else "cli"

# Vazio = padrão de cada backend ("opus" no CLI, claude-opus-5-5 na API).
LLM_MODEL = os.environ.get("COMPANHEIRO_MODEL", "")
# Conversa não precisa pensar muito: "low" deixa a resposta mais rápida.
LLM_EFFORT = os.environ.get("COMPANHEIRO_EFFORT", "low")
