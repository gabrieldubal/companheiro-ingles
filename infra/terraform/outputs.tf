output "proxy_url" {
  description = "Endereço do intermediário: vai no data/proxy.json do app de cada amigo."
  value       = "${trimsuffix(aws_lambda_function_url.proxy.function_url, "/")}/complete"
}

output "table_name" {
  description = "Tabela das chaves e do consumo (usada pelo infra/chaves.py)."
  value       = aws_dynamodb_table.proxy.name
}

output "region" {
  value = var.region
}

output "lambda_role_arn" {
  description = "Role da Lambda: é ela que a role do Bedrock tem que confiar, na opção 2."
  value       = aws_iam_role.lambda.arn
}
