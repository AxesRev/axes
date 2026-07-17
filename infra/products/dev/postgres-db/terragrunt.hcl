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

dependency "eks" {
  config_path = "../eks"

  mock_outputs = {
    cluster_name = "axes-dev"
  }
  mock_outputs_allowed_terraform_commands = ["validate", "plan"]
}

generate "k8s_provider" {
  path      = "k8s_provider.tf"
  if_exists = "overwrite_terragrunt"
  contents  = <<EOF
data "aws_eks_cluster" "this" {
  name = "${dependency.eks.outputs.cluster_name}"
}

data "aws_eks_cluster_auth" "this" {
  name = "${dependency.eks.outputs.cluster_name}"
}

provider "kubernetes" {
  host                   = data.aws_eks_cluster.this.endpoint
  cluster_ca_certificate = base64decode(data.aws_eks_cluster.this.certificate_authority[0].data)
  token                  = data.aws_eks_cluster_auth.this.token
}
EOF
}

locals {
  env = read_terragrunt_config(find_in_parent_folders("env.hcl"))
}

inputs = {
  name            = local.env.locals.database_name
  host            = dependency.rds.outputs.address
  port            = dependency.rds.outputs.port
  master_username = dependency.rds.outputs.master_username
  master_password = dependency.rds.outputs.master_password
  create_app_user = true
  extensions      = ["vector"]
}
