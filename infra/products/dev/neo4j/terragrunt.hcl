include "root" {
  path = find_in_parent_folders("root.hcl")
}

terraform {
  source = "../../../modules/neo4j"
}

dependency "eks" {
  config_path = "../eks"

  mock_outputs = {
    cluster_name = "axes-dev"
  }
  mock_outputs_allowed_terraform_commands = ["validate", "plan"]
}

dependency "neo4j_data" {
  config_path = "../neo4j-data"

  mock_outputs = {
    volume_id         = "vol-mock"
    availability_zone = "eu-west-1a"
    size_gb           = 20
    password          = "mock-password"
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
  namespace          = "neo4j"
  image              = "neo4j:5.26.28-community"
  volume_id          = dependency.neo4j_data.outputs.volume_id
  availability_zone  = dependency.neo4j_data.outputs.availability_zone
  size_gb            = dependency.neo4j_data.outputs.size_gb
  password           = dependency.neo4j_data.outputs.password
}
