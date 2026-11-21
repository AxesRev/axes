include "root" {
  path = find_in_parent_folders("root.hcl")
}

terraform {
  source = "../../../modules/arcadedb"
}

dependency "eks" {
  config_path = "../eks"

  mock_outputs = {
    cluster_name = "axes-dev"
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
  namespace    = "arcadedb"
  image        = "arcadedata/arcadedb:26.11.1"
  storage_size = "20Gi"
}
