include "root" {
  path = find_in_parent_folders("root.hcl")
}

terraform {
  source = "../../../modules//webapp-env"
}

dependency "webapp" {
  config_path = "../webapp"

  mock_outputs = {
    project_id     = "prj_mock"
    team_id        = "team_mock"
    production_url = "https://webapp.example.invalid"
  }
  mock_outputs_allowed_terraform_commands = ["validate", "plan", "destroy"]
}

dependency "tenant" {
  config_path = "../tenant"

  mock_outputs = {
    invoke_url = "https://tenant.example.invalid"
  }
  mock_outputs_allowed_terraform_commands = ["validate", "plan", "destroy"]
}

dependency "billing" {
  config_path = "../billing"

  mock_outputs = {
    invoke_url = "https://billing.example.invalid"
  }
  mock_outputs_allowed_terraform_commands = ["validate", "plan", "destroy"]
}

dependency "integrations" {
  config_path = "../integrations"

  mock_outputs = {
    invoke_url = "https://integrations.example.invalid"
  }
  mock_outputs_allowed_terraform_commands = ["validate", "plan", "destroy"]
}

dependency "generated" {
  config_path = "../generated"

  mock_outputs = {
    parameter_name = "/axes/dev/generated"
  }
  mock_outputs_allowed_terraform_commands = ["validate", "plan", "destroy"]
}

dependency "auth0" {
  config_path = "../auth0"

  mock_outputs = {
    domain        = "example.auth0.com"
    client_id     = "mock-client-id"
    client_secret = "mock-client-secret"
  }
  mock_outputs_allowed_terraform_commands = ["validate", "plan", "destroy"]
}

locals {
  env = read_terragrunt_config(find_in_parent_folders("env.hcl"))
}

inputs = {
  project_id     = dependency.webapp.outputs.project_id
  team_id        = dependency.webapp.outputs.team_id
  production_url = dependency.webapp.outputs.production_url

  tenant_api_url       = dependency.tenant.outputs.invoke_url
  billing_api_url      = dependency.billing.outputs.invoke_url
  integrations_api_url = dependency.integrations.outputs.invoke_url

  auth0_domain        = dependency.auth0.outputs.domain
  auth0_client_id     = dependency.auth0.outputs.client_id
  auth0_client_secret = dependency.auth0.outputs.client_secret

  ssm_secrets_parameter   = "/axes/${local.env.locals.environment}/secrets"
  ssm_generated_parameter = dependency.generated.outputs.parameter_name
  source_path             = "${get_repo_root()}/webapp/axes"
}
