terraform {
  required_version = ">= 1.6.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  # Remote state for real environments (S3 native locking, no DynamoDB table needed):
  # backend "s3" {
  #   bucket       = "my-tfstate-bucket"
  #   key          = "agentic-ai/dev/terraform.tfstate"
  #   region       = "us-east-1"
  #   encrypt      = true
  #   use_lockfile = true
  # }
}

provider "aws" {
  region = var.aws_region

  # $0 mode: lets `terraform plan` run with dummy credentials and no AWS account.
  # Nothing is created - plan only reads provider schemas and computes the diff locally.
  skip_credentials_validation = var.mock_aws
  skip_requesting_account_id  = var.mock_aws
  skip_metadata_api_check     = var.mock_aws
  access_key                  = var.mock_aws ? "mock_access_key" : null
  secret_key                  = var.mock_aws ? "mock_secret_key" : null

  default_tags {
    tags = local.tags
  }
}
