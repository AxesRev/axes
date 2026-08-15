include "root" {
  path = find_in_parent_folders("root.hcl")
}

terraform {
  source = "../../../modules/integrations"
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
      "axes/integrations" = "042993547532.dkr.ecr.eu-west-1.amazonaws.com/axes/integrations"
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
  name = "${local.env.locals.environment}-integrations"

  image = "${dependency.ecr.outputs.repository_urls["axes/integrations"]}:${get_env("INTEGRATIONS_IMAGE_TAG", get_env("IMAGE_TAG", "latest"))}"

  private_subnet_ids           = dependency.vpc.outputs.private_subnets
  db_clients_security_group_id = dependency.vpc.outputs.db_clients_security_group_id

  postgres_host     = dependency.rds.outputs.address
  postgres_port     = dependency.rds.outputs.port
  postgres_db       = dependency.rds.outputs.db_name
  postgres_user     = dependency.rds.outputs.master_username
  postgres_password = dependency.rds.outputs.master_password

  webapp_url = get_env("WEBAPP_URL", "http://localhost:3000")

  slack_client_id     = get_env("SLACK_CLIENT_ID", "")
  slack_client_secret = get_env("SLACK_CLIENT_SECRET", "")

  github_app_slug             = get_env("GITHUB_APP_SLUG", "")
  github_install_state_secret = get_env("GITHUB_INSTALL_STATE_SECRET", "")
  github_client_id            = get_env("GITHUB_CLIENT_ID", "")
  github_client_secret        = get_env("GITHUB_CLIENT_SECRET", "")
  github_oauth_state_secret   = get_env("GITHUB_OAUTH_STATE_SECRET", "")

  salesforce_package_version_id   = get_env("SALESFORCE_PACKAGE_VERSION_ID", "04tg50000008CgjAAE")
  salesforce_install_state_secret = get_env("SALESFORCE_INSTALL_STATE_SECRET", "")
  salesforce_client_id            = get_env("SALESFORCE_CLIENT_ID", "")
  salesforce_private_key          = get_env("SALESFORCE_PRIVATE_KEY", "")
  salesforce_login_url            = get_env("SALESFORCE_LOGIN_URL", "https://login.salesforce.com")
}
