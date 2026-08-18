include "root" {
  path = find_in_parent_folders("root.hcl")
}

terraform {
  source = "../../../modules//billing"
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

dependency "generated" {
  config_path = "../generated"

  mock_outputs = {
    parameter_name = "/axes/dev/generated"
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

  ssm_secrets_parameter   = "/axes/${local.env.locals.environment}/secrets"
  ssm_generated_parameter = dependency.generated.outputs.parameter_name
}
