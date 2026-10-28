# Intermediário do Companheiro de inglês: tudo dentro do nível gratuito da AWS.
#   Lambda (1 milhão de pedidos e 400 mil GB-s por mês grátis) com URL própria (sem custo extra),
#   DynamoDB provisionado em 1 leitura e 1 escrita (dentro dos 25 grátis), log de 7 dias,
#   e um alerta opcional do AWS Budgets (os 2 primeiros orçamentos são grátis).
# Fica de fora tudo que cobra: API Gateway, Secrets Manager, VPC/NAT.
# O consumo do Claude é cobrado pelo Bedrock, na conta das credenciais que você configurar.

terraform {
  required_version = ">= 1.5"
  required_providers {
    aws     = { source = "hashicorp/aws", version = "~> 6.0" }
    archive = { source = "hashicorp/archive", version = "~> 2.4" }
  }
}

provider "aws" {
  region  = var.region
  profile = var.aws_profile == "" ? null : var.aws_profile
}

locals {
  bedrock_region = var.bedrock_region == "" ? var.region : var.bedrock_region
}

data "aws_caller_identity" "me" {}

# --- Tabela: chaves dos amigos (só o hash) e consumo do mês ---------------------------------

resource "aws_dynamodb_table" "proxy" {
  name           = "${var.name}-proxy"
  billing_mode   = "PROVISIONED" # sob demanda não entra no nível gratuito permanente
  read_capacity  = 1
  write_capacity = 1
  hash_key       = "pk"

  attribute {
    name = "pk"
    type = "S"
  }
}

# --- Lambda ----------------------------------------------------------------------------------

data "archive_file" "lambda" {
  type        = "zip"
  source_file = "${path.module}/../lambda/handler.py"
  output_path = "${path.module}/build/handler.zip"
}

resource "aws_iam_role" "lambda" {
  name = "${var.name}-proxy-lambda"
  assume_role_policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Principal = { Service = "lambda.amazonaws.com" }, Action = "sts:AssumeRole" }]
  })
}

resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${var.name}-proxy"
  retention_in_days = var.log_retention_days
}

resource "aws_iam_role_policy" "lambda" {
  name = "${var.name}-proxy"
  role = aws_iam_role.lambda.id
  policy = jsonencode({
    Version   = "2012-10-17"
    Statement = concat(local.base_statements, local.role_statements, local.ssm_statements)
  })
}

locals {
  base_statements = [
    { Effect = "Allow", Action = ["logs:CreateLogStream", "logs:PutLogEvents"], Resource = "${aws_cloudwatch_log_group.lambda.arn}:*" },
    { Effect = "Allow", Action = ["dynamodb:GetItem", "dynamodb:UpdateItem"], Resource = aws_dynamodb_table.proxy.arn },
    # Opção 1 (padrão): o Bedrock desta mesma conta, com a role da própria Lambda.
    { Effect = "Allow", Action = ["bedrock-mantle:CreateInference", "bedrock:InvokeModel"], Resource = "*" },
  ]
  # Opção 2: assumir uma role (que pode ser de outra conta).
  role_statements = [for arn in compact([var.bedrock_role_arn]) : { Effect = "Allow", Action = "sts:AssumeRole", Resource = arn }]
  # Opção 3: chaves guardadas num SecureString do SSM (a chave aws/ssm não cobra).
  ssm_statements = flatten([for p in compact([var.bedrock_secret_param]) : [
    { Effect = "Allow", Action = "ssm:GetParameter",
    Resource = "arn:aws:ssm:${var.region}:${data.aws_caller_identity.me.account_id}:parameter/${trimprefix(p, "/")}" },
    { Effect = "Allow", Action = "kms:Decrypt", Resource = "*",
    Condition = { StringEquals = { "kms:ViaService" = "ssm.${var.region}.amazonaws.com" } } },
  ]])
}

resource "aws_lambda_function" "proxy" {
  function_name    = "${var.name}-proxy"
  role             = aws_iam_role.lambda.arn
  runtime          = "python3.12"
  handler          = "handler.handler"
  filename         = data.archive_file.lambda.output_path
  source_code_hash = data.archive_file.lambda.output_base64sha256
  memory_size      = 256
  timeout          = 120

  environment {
    variables = {
      TABLE_NAME           = aws_dynamodb_table.proxy.name
      BEDROCK_REGION       = local.bedrock_region
      CLAUDE_MODEL         = var.claude_model
      CLAUDE_INVOKE_MODEL  = var.claude_invoke_model
      BEDROCK_API          = var.bedrock_api
      MAX_TOKENS           = tostring(var.max_tokens)
      DEFAULT_LIMIT_USD    = tostring(var.default_limit_usd)
      PRICE_IN_PER_MTOK    = tostring(var.price_in_per_mtok)
      PRICE_OUT_PER_MTOK   = tostring(var.price_out_per_mtok)
      BEDROCK_ROLE_ARN     = var.bedrock_role_arn
      BEDROCK_SECRET_PARAM = var.bedrock_secret_param
    }
  }

  depends_on = [aws_cloudwatch_log_group.lambda, aws_iam_role_policy.lambda]
}

# URL pública: quem não tem uma chave válida recebe 401 do próprio código.
resource "aws_lambda_function_url" "proxy" {
  function_name      = aws_lambda_function.proxy.function_name
  authorization_type = "NONE"
}

# Desde outubro de 2025, a URL precisa das duas permissões; a segunda só vale para chamadas pela URL.
resource "aws_lambda_permission" "url" {
  statement_id           = "FunctionURLAllowPublicAccess"
  action                 = "lambda:InvokeFunctionUrl"
  function_name          = aws_lambda_function.proxy.function_name
  principal              = "*"
  function_url_auth_type = "NONE"
}

resource "aws_lambda_permission" "url_invoke" {
  statement_id             = "FunctionURLInvokeAllowPublicAccess"
  action                   = "lambda:InvokeFunction"
  function_name            = aws_lambda_function.proxy.function_name
  principal                = "*"
  invoked_via_function_url = true
}

# --- Alerta de gasto (opcional) ----------------------------------------------------------------

resource "aws_budgets_budget" "alert" {
  count        = var.alert_email == "" ? 0 : 1
  name         = "${var.name}-mensal"
  budget_type  = "COST"
  limit_amount = tostring(var.alert_monthly_usd)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = [var.alert_email]
  }
}
