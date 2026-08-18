include "root" {
  path = find_in_parent_folders("root.hcl")
}

terraform {
  source = "../../../modules//slack-app"
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
      "axes/slack-app" = "042993547532.dkr.ecr.eu-west-1.amazonaws.com/axes/slack-app"
    }
  }
  mock_outputs_allowed_terraform_commands = ["validate", "plan", "destroy"]
}

dependency "slack-gateway" {
  config_path = "../slack-gateway"

  mock_outputs = {
    invoke_url = "https://example.execute-api.eu-west-1.amazonaws.com"
    node_port  = 30800
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
  image = "${dependency.ecr.outputs.repository_urls["axes/slack-app"]}:${get_env("SLACK_APP_IMAGE_TAG", get_env("IMAGE_TAG", "latest"))}"

  server_url = dependency.slack-gateway.outputs.invoke_url
  node_port  = dependency.slack-gateway.outputs.node_port

  ssm_secrets_parameter   = "/axes/${local.env.locals.environment}/secrets"
  ssm_generated_parameter = dependency.generated.outputs.parameter_name

  integrations_public_url = dependency.integrations.outputs.invoke_url
  manifest_path           = "${get_repo_root()}/slack_app/slack_manifest.json"
  deploy_manifest_script  = "${get_repo_root()}/slack_app/src/slack_app/deploy_manifest.py"
}
