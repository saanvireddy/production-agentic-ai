variable "name" { type = string }
variable "vpc_id" { type = string }
variable "private_subnet_ids" { type = list(string) }
variable "allowed_security_group_ids" { type = map(string) }
variable "db_instance_class" { type = string }
variable "redis_node_type" { type = string }

# ---------------- RDS PostgreSQL 16 (pgvector is available as an extension on RDS) ----------------
resource "random_password" "db" {
  length  = 32
  special = false
}

resource "aws_db_subnet_group" "this" {
  name       = "${var.name}-db"
  subnet_ids = var.private_subnet_ids
}

resource "aws_security_group" "db" {
  name        = "${var.name}-db"
  description = "PostgreSQL from EKS only"
  vpc_id      = var.vpc_id
}

resource "aws_vpc_security_group_ingress_rule" "db" {
  for_each                     = var.allowed_security_group_ids
  security_group_id            = aws_security_group.db.id
  referenced_security_group_id = each.value
  ip_protocol                  = "tcp"
  from_port                    = 5432
  to_port                      = 5432
}

resource "aws_db_parameter_group" "this" {
  name   = "${var.name}-pg16"
  family = "postgres16"
  parameter {
    name  = "rds.force_ssl"
    value = "1"
  }
}

resource "aws_db_instance" "this" {
  identifier                   = "${var.name}-postgres"
  engine                       = "postgres"
  engine_version               = "16"
  instance_class               = var.db_instance_class
  allocated_storage            = 20
  max_allocated_storage        = 100
  storage_type                 = "gp3"
  storage_encrypted            = true
  db_name                      = "agentic"
  username                     = "agentic"
  password                     = random_password.db.result
  db_subnet_group_name         = aws_db_subnet_group.this.name
  vpc_security_group_ids       = [aws_security_group.db.id]
  parameter_group_name         = aws_db_parameter_group.this.name
  publicly_accessible          = false
  multi_az                     = false # true for prod
  backup_retention_period      = 7
  deletion_protection          = false # true for prod
  skip_final_snapshot          = true  # false for prod
  performance_insights_enabled = true
  auto_minor_version_upgrade   = true
}

# ---------------- ElastiCache (Redis OSS) ----------------
resource "aws_elasticache_subnet_group" "this" {
  name       = "${var.name}-redis"
  subnet_ids = var.private_subnet_ids
}

resource "aws_security_group" "redis" {
  name        = "${var.name}-redis"
  description = "Redis from EKS only"
  vpc_id      = var.vpc_id
}

resource "aws_vpc_security_group_ingress_rule" "redis" {
  for_each                     = var.allowed_security_group_ids
  security_group_id            = aws_security_group.redis.id
  referenced_security_group_id = each.value
  ip_protocol                  = "tcp"
  from_port                    = 6379
  to_port                      = 6379
}

resource "aws_elasticache_replication_group" "this" {
  replication_group_id       = "${var.name}-redis"
  description                = "Conversation memory, answer cache and rate limiting"
  engine                     = "redis"
  engine_version             = "7.1"
  node_type                  = var.redis_node_type
  num_cache_clusters         = 1
  port                       = 6379
  subnet_group_name          = aws_elasticache_subnet_group.this.name
  security_group_ids         = [aws_security_group.redis.id]
  at_rest_encryption_enabled = true
  transit_encryption_enabled = true
  automatic_failover_enabled = false
}

output "db_address" { value = aws_db_instance.this.address }
output "db_name" { value = aws_db_instance.this.db_name }
output "db_username" { value = aws_db_instance.this.username }
output "db_password" {
  value     = random_password.db.result
  sensitive = true
}
output "redis_endpoint" { value = aws_elasticache_replication_group.this.primary_endpoint_address }
