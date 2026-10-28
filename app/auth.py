"""Token de acesso: quem está na mesma rede não usa o seu Claude sem ele."""
import secrets

from fastapi import HTTPException, Request

from . import config

_TOKEN_FILE = config.DATA / "token.txt"
if not _TOKEN_FILE.exists():
    _TOKEN_FILE.write_text(secrets.token_urlsafe(16), encoding="utf-8")
TOKEN = _TOKEN_FILE.read_text(encoding="utf-8").strip()


def require_token(request: Request):
    given = request.headers.get("x-token") or request.query_params.get("t") or ""
    if not secrets.compare_digest(given, TOKEN):
        raise HTTPException(401, "Token inválido. Abra o app pelo abrir.bat (ou run.bat): ele já vem com o código de acesso.")
