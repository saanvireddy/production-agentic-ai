locals {
  name = "${var.project}-${var.environment}"
  tags = {
    Project     = var.project
    Environment = var.environment
    ManagedBy   = "terraform"
    Repository  = var.github_repository
  }
}

module "vpc" {
  source             = "./modules/vpc"
  name               = local.name
  cidr               = var.vpc_cidr
  azs                = var.availability_zones
  single_nat_gateway = var.single_nat_gateway
  cluster_name       = local.name
  region             = var.aws_region
}

module "eks" {
  source               = "./modules/eks"
  name                 = local.name
  kubernetes_version   = var.eks_version
  vpc_id               = module.vpc.vpc_id
  private_subnet_ids   = module.vpc.private_subnet_ids
  public_access_cidrs  = var.eks_public_access_cidrs
  node_instance_types  = var.node_instance_types
  node_min_size        = var.node_min_size
  node_desired_size    = var.node_desired_size
  node_max_size        = var.node_max_size
  admin_principal_arns = var.cluster_admin_principal_arns
}

module "ecr" {
  source       = "./modules/ecr"
  repositories = ["production-agentic-ai", "production-agentic-ai-ui"]
}

module "s3" {
  source      = "./modules/s3"
  bucket_name = "${local.name}-documents"
}

module "data" {
  source                     = "./modules/data"
  name                       = local.name
  vpc_id                     = module.vpc.vpc_id
  private_subnet_ids         = module.vpc.private_subnet_ids
  allowed_security_group_ids = { cluster = module.eks.cluster_security_group_id, nodes = module.eks.node_security_group_id }
  db_instance_class          = var.db_instance_class
  redis_node_type            = var.redis_node_type
}

module "secrets" {
  source      = "./modules/secrets"
  name        = var.project
  environment = var.environment
  db_host     = module.data.db_address
  db_name     = module.data.db_name
  db_username = module.data.db_username
  db_password = module.data.db_password
}

module "iam" {
  source              = "./modules/iam"
  name                = local.name
  oidc_provider_arn   = module.eks.oidc_provider_arn
  oidc_issuer_url     = module.eks.oidc_issuer_url
  k8s_namespace       = var.k8s_namespace
  app_secret_arn      = module.secrets.secret_arn
  documents_bucket    = module.s3.bucket_arn
  ecr_repository_arns = values(module.ecr.repository_arns)
  github_repository   = var.github_repository
}
