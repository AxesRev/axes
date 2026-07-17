locals {
  account_vars = read_terragrunt_config(find_in_parent_folders("account.hcl"))
  env_vars     = read_terragrunt_config(find_in_parent_folders("env.hcl"))

  account_id  = local.account_vars.locals.account_id
  aws_region  = local.env_vars.locals.aws_region
  environment = local.env_vars.locals.environment

  common_tags = {
    Project     = "axes"
    Environment = local.environment
    ManagedBy   = "terragrunt"
  }
}

remote_state {
  backend = "s3"

  config = {
    bucket         = "axes-terraform-state-042993547532"
    key            = "${path_relative_to_include()}/terraform.tfstate"
    region         = "eu-west-1"
    dynamodb_table = "axes-terraform-locks"
    encrypt        = true
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
    tags = ${jsonencode(local.common_tags)}
  }
}
EOF
}

inputs = merge(
  local.account_vars.locals,
  local.env_vars.locals,
  {
    tags = local.common_tags
  }
)
