variable "name" { type = string }
variable "environment" { type = string }
variable "db_host" { type = string }
variable "db_name" { type = string }
variable "db_username" { type = string }
variable "db_password" {
  type      = string
  sensitive = true
}

resource "random_password" "jwt" {
  length  = 64
  special = false
}

resource "random_password" "admin" {
  length  = 24
  special = false
}

# One JSON secret consumed by External Secrets Operator (dataFrom.extract) -> Kubernetes Secret.
# Values live in Terraform state too: keep state in an encrypted, access-controlled S3 backend.
resource "aws_secretsmanager_secret" "app" {
  name                    = "${var.name}/${var.environment}/app"
  description             = "Runtime secrets for the Agentic AI API"
  recovery_window_in_days = 7
}

resource "aws_secretsmanager_secret_version" "app" {
  secret_id = aws_secretsmanager_secret.app.id
  secret_string = jsonencode({
    JWT_SECRET        = random_password.jwt.result
    ADMIN_USERNAME    = "admin"
    ADMIN_PASSWORD    = random_password.admin.result
    POSTGRES_USER     = var.db_username
    POSTGRES_PASSWORD = var.db_password
    POSTGRES_DB       = var.db_name
    DATABASE_URL      = "postgresql://${var.db_username}:${var.db_password}@${var.db_host}:5432/${var.db_name}?sslmode=require"
  })
}

output "secret_arn" { value = aws_secretsmanager_secret.app.arn }
output "secret_name" { value = aws_secretsmanager_secret.app.name }
