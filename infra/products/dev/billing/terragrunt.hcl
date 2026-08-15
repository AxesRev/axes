include "root" {
  path = find_in_parent_folders("root.hcl")
}

terraform {
  source = "../../../modules/billing"
}

dependency "vpc" {
  config_path = "../vpc"

  mock_outputs = {
    private_subnets              = ["subnet-a", "subnet-b"]
    db_clients_security_group_id = "sg-mock"
  }
  mock_outputs_allowed_terraform_commands = ["validate", "plan", "destroy"]
}

dependency "ecr" {
  config_path = "../ecr"

  mock_outputs = {
    repository_urls = {
      "axes/billing" = "042993547532.dkr.ecr.eu-west-1.amazonaws.com/axes/billing"
    }
  }
  mock_outputs_allowed_terraform_commands = ["validate", "plan", "destroy"]
}

dependency "rds" {
  config_path = "../rds"

  mock_outputs = {
    address         = "localhost"
    port            = 5432
    db_name         = "axes"
    master_username = "postgres"
    master_password = "mock-password"
  }
  mock_outputs_allowed_terraform_commands = ["validate", "plan", "destroy"]
}

locals {
  env = read_terragrunt_config(find_in_parent_folders("env.hcl"))
}

inputs = {
  name = "${local.env.locals.environment}-billing"

  image = "${dependency.ecr.outputs.repository_urls["axes/billing"]}:${get_env("BILLING_IMAGE_TAG", get_env("IMAGE_TAG", "latest"))}"

  private_subnet_ids           = dependency.vpc.outputs.private_subnets
  db_clients_security_group_id = dependency.vpc.outputs.db_clients_security_group_id

  postgres_host     = dependency.rds.outputs.address
  postgres_port     = dependency.rds.outputs.port
  postgres_db       = dependency.rds.outputs.db_name
  postgres_user     = dependency.rds.outputs.master_username
  postgres_password = dependency.rds.outputs.master_password

  internal_api_secret   = get_env("INTERNAL_API_SECRET", "")
  paddle_api_key        = get_env("PADDLE_API_KEY", "")
  paddle_webhook_secret = get_env("PADDLE_WEBHOOK_SECRET", "")
  paddle_usage_price_id = get_env("PADDLE_USAGE_PRICE_ID", "")
}
