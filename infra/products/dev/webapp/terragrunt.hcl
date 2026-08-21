include "root" {
  path = find_in_parent_folders("root.hcl")
}

terraform {
  source = "../../../modules//webapp"
}

locals {
  env = read_terragrunt_config(find_in_parent_folders("env.hcl"))
}

inputs = {
  name                  = "axes-dev"
  team_id               = "team_7ySilASN9pUBkjj0n2DI60kd"
  ssm_secrets_parameter = "/axes/${local.env.locals.environment}/secrets"
}
