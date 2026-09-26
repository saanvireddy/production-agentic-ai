output "cluster_name" {
  value = module.eks.cluster_name
}

output "cluster_endpoint" {
  value = module.eks.cluster_endpoint
}

output "kubeconfig_command" {
  value = "aws eks update-kubeconfig --region ${var.aws_region} --name ${module.eks.cluster_name}"
}

output "ecr_repository_urls" {
  value = module.ecr.repository_urls
}

output "documents_bucket" {
  value = module.s3.bucket_name
}

output "app_secret_name" {
  description = "Secrets Manager secret synced into Kubernetes by External Secrets (remoteKey in values-aws.yaml)"
  value       = module.secrets.secret_name
}

output "app_irsa_role_arn" {
  description = "Annotate the app ServiceAccount with this role (serviceAccount.annotations in values-aws.yaml)"
  value       = module.iam.app_role_arn
}

output "external_secrets_role_arn" {
  value = module.iam.external_secrets_role_arn
}

output "github_actions_role_arn" {
  description = "Role GitHub Actions assumes via OIDC to push images to ECR (no long-lived keys)"
  value       = module.iam.github_actions_role_arn
}

output "rds_endpoint" {
  value = module.data.db_address
}

output "redis_endpoint" {
  value = module.data.redis_endpoint
}
