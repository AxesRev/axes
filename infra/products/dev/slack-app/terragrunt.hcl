include "root" {
  path = find_in_parent_folders("root.hcl")
}

terraform {
  source = "../../../modules//slack-app"
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
    cluster_name                   = "axes-dev"
    node_security_group_id         = "sg-mock"
    node_autoscaling_group_names   = ["mock-asg"]
  }
  mock_outputs_allowed_terraform_commands = ["validate", "plan", "destroy"]
}

dependency "ecr" {
  config_path = "../ecr"

  mock_outputs = {
    repository_urls = {
      "axes/slack-app" = "042993547532.dkr.ecr.eu-west-1.amazonaws.com/axes/slack-app"
    }
  }
  mock_outputs_allowed_terraform_commands = ["validate", "plan", "destroy"]
}

dependency "integrations" {
  config_path = "../integrations"

  mock_outputs = {
    invoke_url = "https://example.execute-api.eu-west-1.amazonaws.com"
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
  name = "${local.env.locals.environment}-slack"

  vpc_id                       = dependency.vpc.outputs.vpc_id
  vpc_cidr                     = local.env.locals.vpc_cidr
  private_subnet_ids           = dependency.vpc.outputs.private_subnets
  node_security_group_id       = dependency.eks.outputs.node_security_group_id
  node_autoscaling_group_names = dependency.eks.outputs.node_autoscaling_group_names

  image = "${dependency.ecr.outputs.repository_urls["axes/slack-app"]}:${get_env("SLACK_APP_IMAGE_TAG", get_env("IMAGE_TAG", "latest"))}"

  ssm_secrets_parameter   = "/axes/${local.env.locals.environment}/secrets"
  ssm_generated_parameter = "/axes/${local.env.locals.environment}/generated"

  integrations_public_url = dependency.integrations.outputs.invoke_url
}
