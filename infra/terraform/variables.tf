variable "region" {
  description = "Região onde ficam a Lambda e a tabela."
  type        = string
  default     = "us-east-1"
}

variable "aws_profile" {
  description = "Perfil do AWS CLI da conta do intermediário (vazio = credenciais padrão)."
  type        = string
  default     = ""
}

variable "name" {
  description = "Prefixo dos nomes dos recursos."
  type        = string
  default     = "companheiro"
}

# --- Claude no Bedrock ---------------------------------------------------------------------

variable "bedrock_region" {
  description = "Região do endpoint do Claude no Bedrock (vazio = a mesma da Lambda)."
  type        = string
  default     = ""
}

variable "claude_model" {
  description = "Modelo do Claude no Bedrock."
  type        = string
  default     = "anthropic.claude-opus-5-5"
}

variable "bedrock_api" {
  description = "Caminho até o Claude: auto (tenta o endpoint novo e cai no InvokeModel), mantle ou invoke."
  type        = string
  default     = "auto"
}

variable "claude_invoke_model" {
  description = "Perfil de inferência usado no caminho InvokeModel."
  type        = string
  default     = "us.anthropic.claude-opus-5-5"
}

variable "max_tokens" {
  description = "Teto de tokens de resposta por pedido."
  type        = number
  default     = 8000
}

variable "bedrock_role_arn" {
  description = "Opção 2: role a assumir para chamar o Bedrock (pode ser de outra conta). Vazio = não usa."
  type        = string
  default     = ""
}

variable "bedrock_secret_param" {
  description = "Opção 3: nome de um parâmetro SecureString do SSM com {\"access_key_id\", \"secret_access_key\"}. Vazio = não usa."
  type        = string
  default     = ""
}

# --- Limites e preços (só para a conta do limite de cada amigo) ------------------------------

variable "default_limit_usd" {
  description = "Limite mensal padrão por chave, em dólares estimados."
  type        = number
  default     = 5
}

variable "price_in_per_mtok" {
  description = "Preço estimado por milhão de tokens de entrada (confira a tabela do Bedrock)."
  type        = number
  default     = 4
}

variable "price_out_per_mtok" {
  description = "Preço estimado por milhão de tokens de saída."
  type        = number
  default     = 20
}

# --- Gratuito -----------------------------------------------------------------------------------

variable "log_retention_days" {
  description = "Dias de log no CloudWatch (curto, para ficar no nível gratuito)."
  type        = number
  default     = 7
}

variable "alert_email" {
  description = "E-mail para o alerta de gasto do AWS Budgets (vazio = sem alerta)."
  type        = string
  default     = ""
}

variable "alert_monthly_usd" {
  description = "Valor mensal da conta que dispara o alerta."
  type        = number
  default     = 1
}
