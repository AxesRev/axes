include "root" {
  path = find_in_parent_folders("root.hcl")
}

terraform {
  source = "../../../modules//slack-gateway"
}

dependency "vpc" {
  config_path = "../vpc"

  mock_outputs = {
    vpc_id          = "vpc-mock"
    private_subnets = ["subnet-a", "subnet-b"]
  }
  mock_outputs_allowed_terraform_commands = ["validate", "plan", "destroy"]
}

dependency "eks" {
  config_path = "../eks"

  mock_outputs = {
    node_security_group_id       = "sg-mock"
    node_autoscaling_group_names = ["mock-asg"]
  }
  mock_outputs_allowed_terraform_commands = ["validate", "plan", "destroy"]
}

locals {
  env = read_terragrunt_config(find_in_parent_folders("env.hcl"))
}

inputs = {
  name = "${local.env.locals.environment}-slack"

  vpc_id                       = dependency.vpc.outputs.vpc_id
  vpc_cidr                     = local.env.locals.vpc_cidr
  private_subnet_ids           = dependency.vpc.outputs.private_subnets
  node_security_group_id       = dependency.eks.outputs.node_security_group_id
  node_autoscaling_group_names = dependency.eks.outputs.node_autoscaling_group_names
}
