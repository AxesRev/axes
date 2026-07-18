module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 5.0"

  name = var.name
  cidr = var.cidr
  azs  = var.azs

  private_subnets = var.private_subnets
  public_subnets  = var.public_subnets

  enable_nat_gateway   = var.enable_nat_gateway
  single_nat_gateway   = var.single_nat_gateway
  enable_dns_hostnames = true
  enable_dns_support   = true

  public_subnet_tags  = var.public_subnet_tags
  private_subnet_tags = var.private_subnet_tags

  tags = var.tags
}

resource "aws_security_group" "db_clients" {
  name        = "${var.name}-db-clients"
  description = "Clients allowed to reach databases in this VPC"
  vpc_id      = module.vpc.vpc_id
  tags        = merge(var.tags, { Name = "${var.name}-db-clients" })
}
