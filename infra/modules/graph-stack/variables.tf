variable "namespace" {
  description = "Kubernetes namespace for graph services."
  type        = string
  default     = "graph"
}

variable "neo4j_image" {
  description = "Neo4j container image."
  type        = string
  default     = "neo4j:5-community"
}

variable "neo4j_storage_size" {
  description = "Persistent volume size for Neo4j data."
  type        = string
  default     = "20Gi"
}

variable "neo4j_mcp_image" {
  description = "neo4j-mcp container image (ECR)."
  type        = string
}

variable "graph_service_image" {
  description = "graph-service container image (ECR), without MCP."
  type        = string
}

variable "graph_service_command" {
  description = "Container command for graph-service (non-MCP entrypoint)."
  type        = list(string)
  default     = null
}

variable "graph_service_args" {
  description = "Container args for graph-service."
  type        = list(string)
  default     = null
}

variable "neo4j_password" {
  description = "Neo4j password. If null, a random password is generated."
  type        = string
  default     = null
  sensitive   = true
}
