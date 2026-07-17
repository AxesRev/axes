include "root" {
  path = find_in_parent_folders("root.hcl")
}

terraform {
  source = "../../../modules/ecr"
}

inputs = {
  repository_names = [
    "axes/graph-service",
    "axes/neo4j-mcp",
  ]
}
