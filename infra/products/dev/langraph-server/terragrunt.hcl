include "root" {
  path = find_in_parent_folders("root.hcl")
}

# App stack: Terraform lives in this directory (not a reusable module).

dependency "eks" {
  config_path = "../eks"

  mock_outputs = {
    cluster_name = "axes-dev"
  }
  mock_outputs_allowed_terraform_commands = ["validate", "plan"]
}

dependency "ecr" {
  config_path = "../ecr"

  mock_outputs = {
    repository_urls = {
      "axes/langraph-server" = "042993547532.dkr.ecr.eu-west-1.amazonaws.com/axes/langraph-server"
      "axes/neo4j-mcp"       = "042993547532.dkr.ecr.eu-west-1.amazonaws.com/axes/neo4j-mcp"
    }
  }
  mock_outputs_allowed_terraform_commands = ["validate", "plan"]
}

dependency "rds" {
  config_path = "../rds"

  mock_outputs = {
    address = "localhost"
    port    = 5432
  }
  mock_outputs_allowed_terraform_commands = ["validate", "plan"]
}

dependency "postgres-db" {
  config_path = "../postgres-db"

  mock_outputs = {
    name         = "axes"
    app_username = "axes_app"
    app_password = "mock-password"
  }
  mock_outputs_allowed_terraform_commands = ["validate", "plan"]
}

dependency "neo4j-mcp" {
  config_path = "../neo4j-mcp"

  mock_outputs = {
    http_url = "http://neo4j-mcp.neo4j.svc.cluster.local:8811"
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
  image = "${dependency.ecr.outputs.repository_urls["axes/langraph-server"]}:${get_env("IMAGE_TAG", "latest")}"

  postgres_host     = dependency.rds.outputs.address
  postgres_port     = dependency.rds.outputs.port
  postgres_db       = dependency.postgres-db.outputs.name
  postgres_user     = dependency.postgres-db.outputs.app_username
  postgres_password = dependency.postgres-db.outputs.app_password

  neo4j_mcp_host = dependency.neo4j-mcp.outputs.http_url
  auth_type      = "noop"
}
