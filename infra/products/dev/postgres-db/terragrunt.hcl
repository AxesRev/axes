include "root" {
  path = find_in_parent_folders("root.hcl")
}

terraform {
  source = "../../../modules/postgres-db"
}

dependency "rds" {
  config_path = "../rds"

  mock_outputs = {
    address         = "localhost"
    port            = 5432
    master_username = "postgres"
    master_password = "mock-password"
  }
  mock_outputs_allowed_terraform_commands = ["validate", "plan"]
}

generate "postgresql_provider" {
  path      = "postgresql_provider.tf"
  if_exists = "overwrite_terragrunt"
  contents  = <<EOF
provider "postgresql" {
  host            = "${dependency.rds.outputs.address}"
  port            = ${dependency.rds.outputs.port}
  database        = "postgres"
  username        = "${dependency.rds.outputs.master_username}"
  password        = "${dependency.rds.outputs.master_password}"
  sslmode         = "require"
  connect_timeout = 15
  superuser       = false
}
EOF
}

locals {
  env = read_terragrunt_config(find_in_parent_folders("env.hcl"))
}

inputs = {
  name            = local.env.locals.database_name
  create_app_user = true
  extensions      = ["vector"]
}
