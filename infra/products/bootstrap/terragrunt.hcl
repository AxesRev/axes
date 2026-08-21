# Account bootstrap. Apply from a laptop with admin/root creds.
# Do not include ../root.hcl — that remote state backend is the bucket this stack creates.
# Do not add this folder under products/dev; deploy.yml must never apply it.

terraform {
  source = "../../modules/bootstrap"
}

locals {
  account    = read_terragrunt_config(find_in_parent_folders("account.hcl"))
  account_id = local.account.locals.account_id
  aws_region = "eu-west-1"

  tags = {
    Project   = "axes"
    ManagedBy = "terragrunt"
    Component = "bootstrap"
  }
}

remote_state {
  backend = "local"

  config = {
    path = "${get_terragrunt_dir()}/terraform.tfstate"
  }

  generate = {
    path      = "backend.tf"
    if_exists = "overwrite_terragrunt"
  }
}

generate "provider" {
  path      = "provider.tf"
  if_exists = "overwrite_terragrunt"
  contents  = <<EOF
provider "aws" {
  region = "${local.aws_region}"

  default_tags {
    tags = ${jsonencode(local.tags)}
  }
}
EOF
}

inputs = {
  state_bucket_name = "axes-terraform-state-${local.account_id}"
  github_repository = "AxesRev/axes"
  role_name         = "github-actions-deploy"
  tags              = local.tags
}
