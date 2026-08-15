include "root" {
  path = find_in_parent_folders("root.hcl")
}

terraform {
  source = "../../../modules/slack-app"
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

  langraph_api_url = "http://langraph-server.langraph-server.svc.cluster.local:8000"

  postgres_host     = dependency.rds.outputs.address
  postgres_port     = dependency.rds.outputs.port
  postgres_db       = dependency.rds.outputs.db_name
  postgres_user     = dependency.rds.outputs.master_username
  postgres_password = dependency.rds.outputs.master_password

  slack_signing_secret = get_env("SLACK_SIGNING_SECRET", "")
  slack_client_id      = get_env("SLACK_CLIENT_ID", "")
  slack_client_secret  = get_env("SLACK_CLIENT_SECRET", "")
  slack_bot_token      = get_env("SLACK_BOT_TOKEN", "")
  internal_api_secret  = get_env("INTERNAL_API_SECRET", "")
}
