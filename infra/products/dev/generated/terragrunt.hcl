include "root" {
  path = find_in_parent_folders("root.hcl")
}

terraform {
  source = "../../../modules/ssm-generated"
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

dependency "neo4j" {
  config_path = "../neo4j"

  mock_outputs = {
    password = "mock-password"
  }
  mock_outputs_allowed_terraform_commands = ["validate", "plan", "destroy"]
}

locals {
  env = read_terragrunt_config(find_in_parent_folders("env.hcl"))
}

inputs = {
  parameter_name = "/axes/${local.env.locals.environment}/generated"

  values = {
    POSTGRES_HOST     = dependency.rds.outputs.address
    POSTGRES_PORT     = tostring(dependency.rds.outputs.port)
    POSTGRES_DB       = dependency.rds.outputs.db_name
    POSTGRES_USER     = dependency.rds.outputs.master_username
    POSTGRES_PASSWORD = dependency.rds.outputs.master_password

    NEO4J_PASSWORD = dependency.neo4j.outputs.password
    NEO4J_AUTH     = "neo4j/${dependency.neo4j.outputs.password}"
  }
}
