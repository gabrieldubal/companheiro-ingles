"""Leva as credenciais do Claude (do .env) para um SecureString do SSM, onde a Lambda lê.

No .env, além das credenciais do usuário do Terraform (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY),
ficam as do Claude no Bedrock, com nomes próprios para não se misturarem:
    BEDROCK_ACCESS_KEY_ID=...
    BEDROCK_SECRET_ACCESS_KEY=...
    BEDROCK_REGION=us-east-1
    BEDROCK_SESSION_TOKEN=...      (só se forem credenciais temporárias)

Rode pelo com-env.bat, que carrega o .env só para este comando:
    infra\\com-env.bat .venv\\Scripts\\python infra\\bedrock_ssm.py

O parâmetro fica na conta do intermediário (a do Terraform), na região dele, com a chave aws/ssm:
parâmetro padrão e chave gerenciada não cobram. Nada é impresso além do nome e da versão.
Mudou as chaves no .env? Rode de novo: a Lambda pega as novas em até 10 minutos.
"""
import json
import os
import sys

try:
    import boto3
except ImportError:
    sys.exit("Falta o boto3: rode  .venv\\Scripts\\python -m pip install boto3")

NAME = os.environ.get("BEDROCK_SECRET_PARAM", "/companheiro/bedrock")


def main():
    need = ["BEDROCK_ACCESS_KEY_ID", "BEDROCK_SECRET_ACCESS_KEY", "BEDROCK_REGION"]
    missing = [k for k in need if not os.environ.get(k, "").strip()]
    if missing:
        sys.exit("Faltam no .env: " + ", ".join(missing) + ". Rode pelo infra\\com-env.bat.")
    value = {"access_key_id": os.environ["BEDROCK_ACCESS_KEY_ID"].strip(),
             "secret_access_key": os.environ["BEDROCK_SECRET_ACCESS_KEY"].strip(),
             "region": os.environ["BEDROCK_REGION"].strip()}
    if os.environ.get("BEDROCK_SESSION_TOKEN", "").strip():
        value["session_token"] = os.environ["BEDROCK_SESSION_TOKEN"].strip()
    region = os.environ.get("INFRA_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "us-east-1"
    ssm = boto3.client("ssm", region_name=region)
    out = ssm.put_parameter(Name=NAME, Value=json.dumps(value), Type="SecureString", Tier="Standard",
                            Overwrite=True, Description="Credenciais do Claude no Bedrock para o intermediario")
    print(f"Parâmetro {NAME} gravado na região {region} (versão {out['Version']}).")
    print(f"Região do Claude: {value['region']}. No terraform.tfvars: bedrock_secret_param = \"{NAME}\"")


if __name__ == "__main__":
    main()
