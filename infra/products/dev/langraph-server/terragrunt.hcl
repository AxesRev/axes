include "root" {
  path = find_in_parent_folders("root.hcl")
}

terraform {
  source = "${get_repo_root()}/infra//products/dev/langraph-server"
}

dependency "eks" {
  config_path = "../eks"

  mock_outputs = {
    cluster_name = "axes-dev"
  }
  mock_outputs_allowed_terraform_commands = ["validate", "plan", "destroy"]
}

dependency "ecr" {
  config_path = "../ecr"

  mock_outputs = {
    repository_urls = {
      "axes/langraph-server" = "042993547532.dkr.ecr.eu-west-1.amazonaws.com/axes/langraph-server"
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

inputs = {
  image = "${dependency.ecr.outputs.repository_urls["axes/langraph-server"]}:${get_env("LANGRAPH_SERVER_IMAGE_TAG", get_env("IMAGE_TAG", "latest"))}"

  ssm_generated_parameter = dependency.generated.outputs.parameter_name
  ssm_secrets_parameter   = "/axes/${local.env.locals.environment}/secrets"
}
