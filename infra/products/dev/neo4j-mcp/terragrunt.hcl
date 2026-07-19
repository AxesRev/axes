include "root" {
  path = find_in_parent_folders("root.hcl")
}

terraform {
  source = "../../../modules/neo4j-mcp"
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
      "axes/neo4j-mcp" = "042993547532.dkr.ecr.eu-west-1.amazonaws.com/axes/neo4j-mcp"
    }
  }
  mock_outputs_allowed_terraform_commands = ["validate", "plan", "destroy"]
}

dependency "neo4j" {
  config_path = "../neo4j"

  mock_outputs = {
    namespace        = "neo4j"
    bolt_uri         = "bolt://neo4j.neo4j.svc.cluster.local:7687"
    auth_secret_name = "neo4j-auth"
  }
  mock_outputs_allowed_terraform_commands = ["validate", "plan", "destroy"]
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
  namespace         = dependency.neo4j.outputs.namespace
  neo4j_bolt_uri   = dependency.neo4j.outputs.bolt_uri
  auth_secret_name = dependency.neo4j.outputs.auth_secret_name

  image = "${dependency.ecr.outputs.repository_urls["axes/neo4j-mcp"]}:${get_env("NEO4J_MCP_IMAGE_TAG", get_env("IMAGE_TAG", "latest"))}"
}
