include "root" {
  path = find_in_parent_folders("root.hcl")
}

terraform {
  source = "../../../modules/eks"
}

dependency "vpc" {
  config_path = "../vpc"

  mock_outputs = {
    vpc_id                       = "vpc-mock"
    private_subnets              = ["subnet-a", "subnet-b"]
    public_subnets               = ["subnet-c", "subnet-d"]
    db_clients_security_group_id = "sg-mock"
  }
  mock_outputs_allowed_terraform_commands = ["validate", "plan"]
}

locals {
  env = read_terragrunt_config(find_in_parent_folders("env.hcl"))
}

inputs = {
  cluster_name      = local.env.locals.cluster_name
  cluster_version   = "1.31"
  vpc_id            = dependency.vpc.outputs.vpc_id
  subnet_ids        = dependency.vpc.outputs.private_subnets
  public_subnet_ids = dependency.vpc.outputs.public_subnets

  additional_node_security_group_ids = [dependency.vpc.outputs.db_clients_security_group_id]

  node_instance_types = ["t3.small"]
  node_disk_size      = 20
  node_desired_size   = 1
  node_min_size       = 1
  node_max_size       = 4
}
