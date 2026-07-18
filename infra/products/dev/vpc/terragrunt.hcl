include "root" {
  path = find_in_parent_folders("root.hcl")
}

terraform {
  source = "../../../modules/vpc"
}

locals {
  env = read_terragrunt_config(find_in_parent_folders("env.hcl"))
}

inputs = {
  name = local.env.locals.vpc_name
  cidr = local.env.locals.vpc_cidr
  azs  = ["${local.env.locals.aws_region}a", "${local.env.locals.aws_region}b"]

  private_subnets = ["10.20.1.0/24", "10.20.2.0/24"]
  public_subnets  = ["10.20.101.0/24", "10.20.102.0/24"]

  private_subnet_tags = {
    "kubernetes.io/role/internal-elb"                    = "1"
    "kubernetes.io/cluster/${local.env.locals.cluster_name}" = "shared"
  }

  public_subnet_tags = {
    "kubernetes.io/role/elb"                             = "1"
    "kubernetes.io/cluster/${local.env.locals.cluster_name}" = "shared"
  }

  enable_nat_gateway = true
  single_nat_gateway = true
}
