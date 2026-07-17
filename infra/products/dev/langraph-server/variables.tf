variable "namespace" {
  type    = string
  default = "langraph-server"
}

variable "image" {
  description = "Container image from ECR."
  type        = string
}

variable "replicas" {
  type    = number
  default = 1
}

variable "postgres_host" {
  type = string
}

variable "postgres_port" {
  type = number
}

variable "postgres_db" {
  type = string
}

variable "postgres_user" {
  type = string
}

variable "postgres_password" {
  type      = string
  sensitive = true
}

variable "neo4j_mcp_host" {
  description = "In-cluster Neo4j MCP HTTP base URL."
  type        = string
  default     = ""
}

variable "auth_type" {
  type    = string
  default = "noop"
}
