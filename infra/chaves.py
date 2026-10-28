"""Chaves dos amigos no intermediário: criar, listar com o consumo do mês, mudar o limite e revogar.

Roda no seu PC, com as credenciais da conta do intermediário (as mesmas do Terraform):
    python chaves.py nova "Ana" --limite 5
    python chaves.py listar
    python chaves.py limite "Ana" 10
    python chaves.py revogar "Ana"

A chave aparece uma vez só, na criação: na tabela fica apenas o hash dela.
Precisa do boto3 (pip install boto3). Perfil e região: --perfil e --regiao, ou AWS_PROFILE/AWS_REGION.
"""
import argparse
import base64
import hashlib
import json
import secrets
import sys
from datetime import datetime, timezone
from decimal import Decimal

try:
    import boto3
except ImportError:
    sys.exit("Falta o boto3: rode  pip install boto3")


def table(args):
    session = boto3.Session(profile_name=args.perfil or None, region_name=args.regiao or None)
    return session.resource("dynamodb").Table(args.tabela)


def keys(t):
    items, kw = [], {}
    while True:
        page = t.scan(**kw)
        items += page.get("Items", [])
        if "LastEvaluatedKey" not in page:
            return items
        kw["ExclusiveStartKey"] = page["LastEvaluatedKey"]


def find(t, name):
    hits = [i for i in keys(t) if i["pk"].startswith("key#") and i.get("name", "").lower() == name.lower()]
    if not hits:
        sys.exit(f"Nenhuma chave com o nome {name!r}.")
    return hits[0]


def cmd_nova(args):
    t = table(args)
    if any(i["pk"].startswith("key#") and i.get("name", "").lower() == args.nome.lower() for i in keys(t)):
        sys.exit(f"Já existe uma chave com o nome {args.nome!r}. Revogue antes ou use outro nome.")
    key = "ci_" + secrets.token_urlsafe(24)
    t.put_item(Item={"pk": "key#" + hashlib.sha256(key.encode()).hexdigest(), "name": args.nome,
                     "limit_usd": Decimal(str(args.limite)), "active": True,
                     "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
    print(f"Chave de {args.nome} (limite US$ {args.limite:.2f} por mês). Ela não aparece de novo:\n")
    print(key)
    if args.url:
        raw = json.dumps({"url": args.url, "key": key}, separators=(",", ":")).encode()
        code = "CI1-" + base64.urlsafe_b64encode(raw).decode().rstrip("=")
        print("\nCódigo do app (mande para a pessoa por um canal privado; ela cola na tela de boas-vindas):\n")
        print(code)
        print("\nOu, se preferir, o conteúdo do data/proxy.json:\n")
        print(json.dumps({"url": args.url, "key": key}, indent=2))


def cmd_listar(args):
    t = table(args)
    items = keys(t)
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    usage = {i["pk"].split("#")[1]: i for i in items if i["pk"].startswith("use#") and i["pk"].endswith(month)}
    rows = [i for i in items if i["pk"].startswith("key#")]
    if not rows:
        print("Nenhuma chave ainda.")
        return
    print(f"{'nome':20} {'ativa':6} {'limite':>8} {'gasto ' + month:>14} {'pedidos':>8}")
    for i in sorted(rows, key=lambda r: r.get("name", "")):
        u = usage.get(i["pk"].split("#")[1], {})
        print(f"{i.get('name', '?'):20} {'sim' if i.get('active', True) else 'não':6} "
              f"{float(i.get('limit_usd', 0)):>8.2f} {float(u.get('cost_usd', 0)):>14.4f} {int(u.get('requests', 0)):>8}")


def cmd_limite(args):
    t = table(args)
    i = find(t, args.nome)
    t.update_item(Key={"pk": i["pk"]}, UpdateExpression="SET limit_usd = :l",
                  ExpressionAttributeValues={":l": Decimal(str(args.valor))})
    print(f"Limite de {args.nome}: US$ {args.valor:.2f} por mês.")


def cmd_revogar(args):
    t = table(args)
    i = find(t, args.nome)
    t.update_item(Key={"pk": i["pk"]}, UpdateExpression="SET active = :f", ExpressionAttributeValues={":f": False})
    print(f"Chave de {args.nome} revogada. O app dessa pessoa para de falar com o Claude na hora.")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--tabela", default="companheiro-proxy")
    p.add_argument("--perfil", default="")
    p.add_argument("--regiao", default="")
    sub = p.add_subparsers(dest="cmd", required=True)
    n = sub.add_parser("nova", help="cria a chave de uma pessoa")
    n.add_argument("nome")
    n.add_argument("--limite", type=float, default=5.0, help="limite mensal em dólares estimados")
    n.add_argument("--url", default="", help="o proxy_url do Terraform, para já imprimir o proxy.json")
    sub.add_parser("listar", help="chaves e o consumo deste mês")
    lim = sub.add_parser("limite", help="muda o limite mensal")
    lim.add_argument("nome")
    lim.add_argument("valor", type=float)
    r = sub.add_parser("revogar", help="desliga a chave de uma pessoa")
    r.add_argument("nome")
    args = p.parse_args()
    {"nova": cmd_nova, "listar": cmd_listar, "limite": cmd_limite, "revogar": cmd_revogar}[args.cmd](args)


if __name__ == "__main__":
    main()
