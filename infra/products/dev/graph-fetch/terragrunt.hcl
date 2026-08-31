include "root" {
  path = find_in_parent_folders("root.hcl")
}

terraform {
  source = "../../../modules/graph-fetch"
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
      "axes/graph-service" = "042993547532.dkr.ecr.eu-west-1.amazonaws.com/axes/graph-service"
    }
  }
  mock_outputs_allowed_terraform_commands = ["validate", "plan", "destroy"]
}

dependency "neo4j" {
  config_path = "../neo4j"

  mock_outputs = {
    bolt_uri        = "bolt://neo4j.neo4j.svc.cluster.local:7687"
    statefulset_uid = "00000000-0000-0000-0000-000000000000"
    password        = "mock-password"
  }
  mock_outputs_allowed_terraform_commands = ["validate", "plan", "destroy"]
}

dependency "langraph-server" {
  config_path = "../langraph-server"

  mock_outputs = {
    namespace              = "langraph-server"
    postgres_secret_name   = "langraph-server-postgres"
    github_secret_name     = "langraph-server-github"
    salesforce_secret_name = "langraph-server-salesforce"
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
  namespace = dependency.langraph-server.outputs.namespace
  image     = "${dependency.ecr.outputs.repository_urls["axes/graph-service"]}:${get_env("GRAPH_SERVICE_IMAGE_TAG", get_env("IMAGE_TAG", "latest"))}"

  bolt_uri       = dependency.neo4j.outputs.bolt_uri
  neo4j_uid      = dependency.neo4j.outputs.statefulset_uid
  neo4j_password = dependency.neo4j.outputs.password

  postgres_secret_name   = dependency.langraph-server.outputs.postgres_secret_name
  github_secret_name     = dependency.langraph-server.outputs.github_secret_name
  salesforce_secret_name = dependency.langraph-server.outputs.salesforce_secret_name
}
