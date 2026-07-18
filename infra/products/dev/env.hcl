locals {
  environment   = "dev"
  aws_region    = "eu-west-1"
  vpc_name      = "axes-dev"
  cluster_name       = "axes-dev"
  kubernetes_version = "1.36"
  vpc_cidr      = "10.20.0.0/16"
  database_name = "axes"

  neo4j_mcp_host = "http://neo4j-mcp.neo4j.svc.cluster.local:8811"
}
