"""Intermediário entre o app dos amigos e o Claude no Bedrock.

O app de cada amigo manda {system, prompt, schema, effort} com a chave pessoal dele no cabeçalho
Authorization. Aqui: confere a chave (guardada só como hash), confere o limite do mês, chama o
Claude no Bedrock com as credenciais configuradas e anota o consumo. O texto dos pedidos não é
gravado em lugar nenhum: o log tem só quem pediu (o começo do hash), tokens e tempo.

Sem dependências além do que a Lambda já traz (boto3/botocore). Dois caminhos para o Bedrock:
  - "mantle": o endpoint de Messages do Claude no Bedrock (bedrock-mantle:CreateInference);
  - "invoke": o InvokeModel clássico do bedrock-runtime (bedrock:InvokeModel), com um perfil de
    inferência como us.anthropic.claude-opus-5-5. É o que credenciais antigas costumam permitir.
  "auto" tenta o primeiro e, se as credenciais não tiverem a permissão dele, fica no segundo.
"""
import base64
import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from decimal import Decimal

import boto3
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from botocore.config import Config
from botocore.credentials import Credentials
from botocore.exceptions import ClientError
from botocore.session import get_session

TABLE = os.environ.get("TABLE_NAME", "companheiro-proxy")
BEDROCK_REGION = os.environ.get("BEDROCK_REGION") or os.environ.get("AWS_REGION", "us-east-1")
MODEL = os.environ.get("CLAUDE_MODEL", "anthropic.claude-opus-5-5")
INVOKE_MODEL = os.environ.get("CLAUDE_INVOKE_MODEL", "us.anthropic.claude-opus-5-5")
BEDROCK_API = os.environ.get("BEDROCK_API", "auto")  # auto, mantle ou invoke
MAX_TOKENS = int(os.environ.get("MAX_TOKENS", "8000"))
DEFAULT_LIMIT_USD = float(os.environ.get("DEFAULT_LIMIT_USD", "5"))
PRICE_IN = float(os.environ.get("PRICE_IN_PER_MTOK", "4"))     # US$ por milhão de tokens de entrada
PRICE_OUT = float(os.environ.get("PRICE_OUT_PER_MTOK", "20"))  # e de saída (confira a tabela do Bedrock)
ROLE_ARN = os.environ.get("BEDROCK_ROLE_ARN", "")          # opção 2: assumir uma role (pode ser de outra conta)
SECRET_PARAM = os.environ.get("BEDROCK_SECRET_PARAM", "")  # opção 3: chaves num SecureString do SSM
MAX_PROMPT_CHARS = int(os.environ.get("MAX_PROMPT_CHARS", "120000"))
EFFORTS = {"low", "medium", "high"}

_table = None
_creds = {"value": None, "until": 0.0, "region": None}
_mode = {"api": None}  # no modo auto: o caminho que funcionou, para não repetir a tentativa


def _db():
    global _table
    if _table is None:
        _table = boto3.resource("dynamodb").Table(TABLE)
    return _table


def _resp(status: int, body: dict) -> dict:
    return {"statusCode": status, "headers": {"content-type": "application/json"},
            "body": json.dumps(body, ensure_ascii=False)}


def _hash(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def _credentials():
    """As credenciais do Bedrock: a role da própria Lambda, uma role assumida ou chaves do SSM."""
    now = time.time()
    if _creds["value"] and now < _creds["until"]:
        return _creds["value"]
    region = None
    if ROLE_ARN:
        c = boto3.client("sts").assume_role(RoleArn=ROLE_ARN, RoleSessionName="companheiro-proxy")["Credentials"]
        value = Credentials(c["AccessKeyId"], c["SecretAccessKey"], c["SessionToken"])
        until = c["Expiration"].timestamp() - 300
    elif SECRET_PARAM:
        raw = boto3.client("ssm").get_parameter(Name=SECRET_PARAM, WithDecryption=True)["Parameter"]["Value"]
        d = json.loads(raw)
        value = Credentials(d["access_key_id"], d["secret_access_key"], d.get("session_token") or None)
        region = d.get("region") or None  # a região do Claude pode vir junto com as chaves
        until = now + 600
    else:
        value = get_session().get_credentials().get_frozen_credentials()
        until = now + 300
    _creds.update(value=value, until=until, region=region)
    return value


def call_claude(payload: dict) -> tuple[int, dict]:
    if BEDROCK_API == "invoke" or _mode["api"] == "invoke":
        return _invoke(payload)
    status, data = _mantle(payload)
    if BEDROCK_API == "auto" and status == 403 and "bedrock-mantle" in json.dumps(data):
        _mode["api"] = "invoke"  # as credenciais só têm o InvokeModel
        return _invoke(payload)
    return status, data


def _invoke(payload: dict) -> tuple[int, dict]:
    """InvokeModel clássico: o mesmo corpo da Messages API, com anthropic_version e sem o model."""
    creds = _credentials()
    region = _creds["region"] or BEDROCK_REGION
    client = boto3.client("bedrock-runtime", region_name=region, aws_access_key_id=creds.access_key,
                          aws_secret_access_key=creds.secret_key, aws_session_token=creds.token,
                          config=Config(read_timeout=110, connect_timeout=10, retries={"max_attempts": 2}))
    body = {k: v for k, v in payload.items() if k != "model"}
    body["anthropic_version"] = "bedrock-2023-05-31"
    try:
        r = client.invoke_model(modelId=INVOKE_MODEL, body=json.dumps(body), contentType="application/json",
                                accept="application/json")
        return 200, json.loads(r["body"].read())
    except ClientError as e:
        return e.response.get("ResponseMetadata", {}).get("HTTPStatusCode", 502), \
            {"error": {"message": e.response.get("Error", {}).get("Message", str(e))}}


def _mantle(payload: dict) -> tuple[int, dict]:
    """POST assinado (SigV4, serviço bedrock-mantle) no endpoint de Messages do Claude no Bedrock."""
    creds = _credentials()
    region = _creds["region"] or BEDROCK_REGION
    url = f"https://bedrock-mantle.{region}.api.aws/anthropic/v1/messages"
    data = json.dumps(payload).encode()
    req = AWSRequest(method="POST", url=url, data=data,
                     headers={"content-type": "application/json", "anthropic-version": "2023-06-01"})
    SigV4Auth(creds, "bedrock-mantle", region).add_auth(req)
    http = urllib.request.Request(url, data=data, headers=dict(req.headers.items()), method="POST")
    try:
        with urllib.request.urlopen(http, timeout=110) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except ValueError:
            return e.code, {"error": {"message": str(e)}}


def _month() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def handler(event, context):
    http = (event.get("requestContext") or {}).get("http") or {}
    if http.get("method") != "POST" or event.get("rawPath", "/") not in ("/", "/complete"):
        return _resp(404, {"error": "Use POST /complete."})
    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    token = headers.get("authorization", "").removeprefix("Bearer ").strip()
    if not token:
        return _resp(401, {"error": "Falta a chave do app."})
    h = _hash(token)
    item = _db().get_item(Key={"pk": f"key#{h}"}).get("Item")
    if not item or not item.get("active", True):
        return _resp(401, {"error": "Chave do app inválida ou revogada."})
    month = _month()
    usage_key = {"pk": f"use#{h}#{month}"}
    usage = _db().get_item(Key=usage_key).get("Item") or {}
    limit = float(item.get("limit_usd", DEFAULT_LIMIT_USD))
    spent = float(usage.get("cost_usd", 0))
    if spent >= limit:
        return _resp(402, {"error": f"O limite deste mês (US$ {limit:.2f}) acabou. Ele volta no dia 1.",
                           "spent": spent, "limit": limit})

    raw = event.get("body") or ""
    if event.get("isBase64Encoded"):
        raw = base64.b64decode(raw).decode()
    try:
        body = json.loads(raw)
        system, prompt, schema = str(body["system"]), str(body["prompt"]), body["schema"]
    except (ValueError, KeyError, TypeError):
        return _resp(400, {"error": "Pedido inválido: precisa de system, prompt e schema."})
    if not isinstance(schema, dict) or len(system) + len(prompt) > MAX_PROMPT_CHARS:
        return _resp(400, {"error": "Pedido grande demais ou schema inválido."})
    effort = body.get("effort") if body.get("effort") in EFFORTS else "low"

    t0 = time.time()
    status, data = call_claude({
        "model": MODEL, "max_tokens": MAX_TOKENS, "system": system,
        "messages": [{"role": "user", "content": prompt}],
        "output_config": {"effort": effort, "format": {"type": "json_schema", "schema": schema}},
    })
    took = round(time.time() - t0, 1)
    u = data.get("usage") or {}
    tin = int(u.get("input_tokens", 0)) + int(u.get("cache_creation_input_tokens", 0) or 0) + \
        int(u.get("cache_read_input_tokens", 0) or 0)
    tout = int(u.get("output_tokens", 0))
    cost = tin * PRICE_IN / 1e6 + tout * PRICE_OUT / 1e6
    if tin or tout:
        _db().update_item(
            Key=usage_key,
            UpdateExpression="ADD requests :one, tokens_in :i, tokens_out :o, cost_usd :c",
            ExpressionAttributeValues={":one": 1, ":i": tin, ":o": tout, ":c": Decimal(str(round(cost, 6)))},
        )
    print(json.dumps({"who": h[:8], "name": item.get("name", ""), "status": status, "in": tin, "out": tout,
                      "usd": round(cost, 4), "s": took}))
    if status != 200:
        msg = (data.get("error") or {}).get("message", "") if isinstance(data.get("error"), dict) else str(data.get("error", ""))
        code = 429 if status == 429 else 502
        return _resp(code, {"error": f"O Claude respondeu {status}: {msg[:300]}"})
    if data.get("stop_reason") == "refusal":
        return _resp(502, {"error": "O modelo recusou esta resposta. Tente reformular."})
    text = next((b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"), "")
    try:
        parsed = json.loads(text)
    except ValueError:
        return _resp(502, {"error": "O Claude não devolveu JSON válido."})
    return _resp(200, {"data": parsed, "usage": {"input_tokens": tin, "output_tokens": tout},
                       "month": {"spent": round(spent + cost, 4), "limit": limit}})
