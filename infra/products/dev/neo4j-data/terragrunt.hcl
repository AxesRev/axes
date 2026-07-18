include "root" {
  path = find_in_parent_folders("root.hcl")
}

terraform {
  source = "../../../modules/neo4j-data"
}

dependency "vpc" {
  config_path = "../vpc"

  mock_outputs = {
    azs = ["eu-west-1a", "eu-west-1b"]
  }
  mock_outputs_allowed_terraform_commands = ["validate", "plan"]
}

locals {
  env = read_terragrunt_config(find_in_parent_folders("env.hcl"))
}

inputs = {
  name              = "${local.env.locals.cluster_name}-neo4j-data"
  availability_zone = dependency.vpc.outputs.azs[0]
  size_gb           = 20
}
