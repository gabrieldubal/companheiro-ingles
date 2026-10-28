# Intermediário: o app dos amigos usando o Claude sem as suas credenciais

O app continua rodando no computador de cada pessoa (Whisper, detector de fonemas, banco, áudios e
cartões ficam na pasta `data/` dela). Só uma peça fica online: uma Lambda que guarda o acesso ao
Claude no Bedrock e dá a cada amigo uma chave pessoal, com limite por mês e revogável.

```
 PC do amigo                           Conta AWS do intermediário            Bedrock
 app (data/proxy.json: url + chave) ──▶ Lambda (URL própria) ──▶ confere a chave ──▶ Claude
                                         DynamoDB: hash das chaves e consumo do mês
```

- A chave do amigo abre só o intermediário. O modelo e o tamanho da resposta são fixos lá dentro.
- Na tabela fica só o hash da chave. A chave aparece uma vez, quando você cria.
- O texto dos pedidos não é gravado. O log tem o começo do hash, o nome, os tokens e o tempo.

## Custo da infra: zero

Tudo fica dentro do nível gratuito permanente da AWS:

| Recurso | Configuração | Grátis por mês |
|---|---|---|
| Lambda | 256 MB, até 120 s por pedido | 1 milhão de pedidos e 400 mil GB-s: a Lambda espera o Claude, então uns 100 mil pedidos de 15 s |
| URL da Lambda | autenticação no código | sem custo extra |
| DynamoDB | provisionado, 1 leitura e 1 escrita | 25 de cada e 25 GB |
| CloudWatch Logs | 7 dias de retenção | 5 GB |
| AWS Budgets (opcional) | 1 alerta | os 2 primeiros orçamentos |
| SSM SecureString (só na opção 3) | parâmetro padrão, chave `aws/ssm` | sem custo |

Fica de fora tudo que cobra: API Gateway, Secrets Manager, VPC e NAT. O consumo do Claude é cobrado
pelo Bedrock, na conta das credenciais que você configurar.

## Passo a passo

### 1. A conta nova

1. Crie a conta da AWS (o plano gratuito serve) e ligue o MFA no usuário principal (root).
2. Em Billing, crie um "Zero spend budget": avisa se qualquer centavo for cobrado.
3. Crie um usuário IAM só para o Terraform, com permissão de administrador, e gere uma chave de acesso.
4. Ponha as credenciais no `.env` da pasta do app (`AWS_ACCESS_KEY_ID` e `AWS_SECRET_ACCESS_KEY`).
   O `infra\com-env.bat` carrega o `.env` só durante cada comando, sem gravar perfil; o `.env` está
   no `.gitignore` e não vai no pacote dos amigos.

O plano gratuito fecha a conta depois de 6 meses. Se o intermediário estiver em uso, passe para o
plano pago antes disso: sem mensalidade, e o uso continua dentro do nível sempre gratuito.

### 2. As credenciais do Claude: escolha uma

- **Opção 1, o Bedrock da própria conta nova** (padrão). Libere os modelos da Anthropic no console do
  Bedrock dessa conta. A Lambda usa a role dela; não há chave nenhuma guardada.
- **Opção 2, uma role de outra conta** (sem chaves). Na conta que paga o Bedrock, crie uma role com
  permissão `bedrock-mantle:CreateInference` e uma relação de confiança com a role da Lambda (o
  Terraform mostra o ARN dela em `lambda_role_arn`). Depois, ponha o ARN dessa role em
  `bedrock_role_arn` e rode o `terraform apply` de novo. Exemplo da relação de confiança:

  ```json
  {
    "Version": "2012-10-17",
    "Statement": [{
      "Effect": "Allow",
      "Principal": { "AWS": "arn:aws:iam::<conta-do-intermediario>:role/companheiro-proxy-lambda" },
      "Action": "sts:AssumeRole"
    }]
  }
  ```
- **Opção 3, chaves de acesso no `.env`** (a que está configurada). No `.env` da pasta do app,
  com nomes próprios para não se misturarem às do Terraform:

  ```
  BEDROCK_ACCESS_KEY_ID=...
  BEDROCK_SECRET_ACCESS_KEY=...
  BEDROCK_REGION=us-east-1
  ```

  A Lambda roda na AWS e não enxerga o `.env`. Por isso, um script leva as chaves para um parâmetro
  SecureString do SSM na conta do intermediário (grátis), e a Lambda lê de lá. As chaves não
  passam pelo Terraform, que as guardaria em texto aberto no arquivo de estado:

  ```bash
  infra\com-env.bat .venv\Scripts\python infra\bedrock_ssm.py
  ```

  Mudou as chaves? Rode o script de novo: a Lambda pega as novas em até 10 minutos. As chaves
  precisam ser de um usuário com permissão `bedrock-mantle:CreateInference` na conta do Bedrock.

**Qual caminho até o Claude.** O intermediário sabe falar com o Claude no Bedrock de dois jeitos:
pelo endpoint novo de Messages (permissão `bedrock-mantle:CreateInference`) ou pelo InvokeModel
clássico (permissão `bedrock:InvokeModel`, com um perfil de inferência como
`us.anthropic.claude-opus-5-5`). Com `bedrock_api = "auto"` ele tenta o primeiro e, se as chaves
não tiverem a permissão, passa para o segundo. As chaves configuradas em 27/10 só têm o clássico,
então o `terraform.tfvars` está com `bedrock_api = "invoke"`.

### 3. Subir o intermediário

```bash
copy infra\terraform\terraform.tfvars.example infra\terraform\terraform.tfvars
infra\com-env.bat terraform -chdir=infra\terraform init
infra\com-env.bat terraform -chdir=infra\terraform apply
```

No fim, o Terraform mostra o `proxy_url`. Guarde esse endereço.

### 4. Testar com uma chave sua

```bash
infra\com-env.bat .venv\Scripts\python infra\chaves.py nova "Teste" --url <proxy_url>
```

O comando imprime o conteúdo de um `proxy.json`. Para testar sem mexer no seu app, use uma cópia dos
dados: crie uma pasta, salve o `proxy.json` nela e ligue o app com `COMPANHEIRO_DATA` apontando para
essa pasta. No seu app de sempre, não crie `data/proxy.json`: com esse arquivo, o app passa a usar o
intermediário em vez do Claude Code.

### 5. Um amigo

```bash
infra\com-env.bat .venv\Scripts\python infra\chaves.py nova "Ana" --limite 5 --url <proxy_url>
```

Mande o `proxy.json` para a pessoa por um canal privado. Ele vai na pasta `data/` do app dela.

## No dia a dia

```bash
infra\com-env.bat .venv\Scripts\python infra\chaves.py listar              # quem gastou quanto neste mês
infra\com-env.bat .venv\Scripts\python infra\chaves.py limite "Ana" 10      # muda o limite mensal
infra\com-env.bat .venv\Scripts\python infra\chaves.py revogar "Ana"        # corta na hora
```

- O limite é contado em dólares estimados, com os preços de `price_in_per_mtok` e `price_out_per_mtok`.
  Ajuste esses preços para os da tabela do Bedrock do modelo que você usa.
- Quando o limite acaba, o app da pessoa mostra "O limite deste mês acabou". Ele volta no dia 1 (UTC).
- Para desmontar tudo: `terraform destroy` em `infra/terraform`.

## Arquivos

| Arquivo | O que faz |
|---|---|
| `lambda/handler.py` | A Lambda: confere a chave e o limite, chama o Claude no Bedrock (SigV4, sem pacotes extras) e anota o consumo |
| `terraform/` | Tabela, role, log, Lambda, URL, permissões e o alerta opcional |
| `chaves.py` | Criar, listar, mudar o limite e revogar as chaves dos amigos |
| `bedrock_ssm.py` | Leva as credenciais do Claude do `.env` para o SSM |
| `com-env.bat` | Roda um comando com o `.env` carregado só para ele |
