include "root" {
  path = find_in_parent_folders("root.hcl")
}

terraform {
  source = "../../../modules/graph-stack"
}

dependency "eks" {
  config_path = "../eks"

  mock_outputs = {
    cluster_name                       = "axes-dev"
    cluster_endpoint                   = "https://example.eks.amazonaws.com"
    cluster_certificate_authority_data = "bW9jaw=="
  }
  mock_outputs_allowed_terraform_commands = ["validate", "plan"]
}

dependency "ecr" {
  config_path = "../ecr"

  mock_outputs = {
    repository_urls = {
      "axes/graph-service" = "042993547532.dkr.ecr.eu-west-1.amazonaws.com/axes/graph-service"
      "axes/neo4j-mcp"     = "042993547532.dkr.ecr.eu-west-1.amazonaws.com/axes/neo4j-mcp"
    }
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

inputs = {
  namespace           = "graph"
  neo4j_image        = "neo4j:5-community"
  neo4j_storage_size = "20Gi"

  # Images must be pushed to ECR before applying this stack.
  neo4j_mcp_image     = "${dependency.ecr.outputs.repository_urls["axes/neo4j-mcp"]}:latest"
  graph_service_image = "${dependency.ecr.outputs.repository_urls["axes/graph-service"]}:latest"

  # graph-service non-MCP entrypoint is not defined yet; override when Dockerfile/CMD exists.
  graph_service_command = null
  graph_service_args    = null
}
