variable "namespace" {
  description = "Kubernetes namespace (typically the Neo4j namespace)."
  type        = string
}

variable "image" {
  description = "neo4j-mcp container image (ECR)."
  type        = string
}

variable "neo4j_bolt_uri" {
  description = "Bolt URI for the Neo4j service."
  type        = string
}

variable "auth_secret_name" {
  description = "Kubernetes secret name with NEO4J_USER and NEO4J_PASSWORD."
  type        = string
}

variable "replicas" {
  description = "Number of MCP replicas."
  type        = number
  default     = 1
}
