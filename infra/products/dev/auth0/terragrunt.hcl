include "root" {
  path = find_in_parent_folders("root.hcl")
}

terraform {
  source = "../../../modules//auth0"
}

dependency "webapp" {
  config_path = "../webapp"

  mock_outputs = {
    production_url = "https://webapp.example.invalid"
  }
  mock_outputs_allowed_terraform_commands = ["validate", "plan", "destroy"]
}

locals {
  env = read_terragrunt_config(find_in_parent_folders("env.hcl"))
}

inputs = {
  name                  = "Axes"
  production_url        = dependency.webapp.outputs.production_url
  ssm_secrets_parameter = "/axes/${local.env.locals.environment}/secrets"
}
