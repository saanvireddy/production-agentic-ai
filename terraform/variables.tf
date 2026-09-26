variable "project" {
  description = "Project name, used as a prefix for all resources"
  type        = string
  default     = "agentic-ai"
}

variable "environment" {
  description = "Deployment environment"
  type        = string
  default     = "dev"
  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "environment must be dev, staging or prod."
  }
}

variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "mock_aws" {
  description = "Plan without an AWS account (dummy credentials, no API calls). Set false for real deployments."
  type        = bool
  default     = true
}

# ---- Network ----
variable "vpc_cidr" {
  description = "CIDR block of the VPC"
  type        = string
  default     = "10.40.0.0/16"
}

variable "availability_zones" {
  description = "AZs to spread subnets across (static list so plan needs no AWS API call)"
  type        = list(string)
  default     = ["us-east-1a", "us-east-1b"]
}

variable "single_nat_gateway" {
  description = "One shared NAT gateway (cheaper) instead of one per AZ (highly available)"
  type        = bool
  default     = true
}

# ---- EKS ----
variable "eks_version" {
  description = "Kubernetes version for the EKS control plane"
  type        = string
  default     = "1.33"
}

variable "node_instance_types" {
  description = "Instance types for the managed node group"
  type        = list(string)
  default     = ["t3.large"]
}

variable "node_min_size" {
  type    = number
  default = 2
}

variable "node_desired_size" {
  type    = number
  default = 2
}

variable "node_max_size" {
  type    = number
  default = 5
}

variable "cluster_admin_principal_arns" {
  description = "IAM principals granted cluster-admin via EKS access entries"
  type        = list(string)
  default     = []
}

variable "eks_public_access_cidrs" {
  description = "CIDRs allowed to reach the public EKS API endpoint"
  type        = list(string)
  default     = ["0.0.0.0/0"]
}

# ---- Data ----
variable "db_instance_class" {
  type    = string
  default = "db.t4g.micro"
}

variable "redis_node_type" {
  type    = string
  default = "cache.t4g.micro"
}

# ---- CI/CD ----
variable "github_repository" {
  description = "owner/repo allowed to push images to ECR via GitHub OIDC"
  type        = string
  default     = "your-github-user/production-agentic-ai"
}

variable "k8s_namespace" {
  description = "Namespace the application runs in (for IRSA trust policies)"
  type        = string
  default     = "agentic-ai"
}
