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

variable "ssm_generated_parameter" {
  description = "Terraform-owned SSM SecureString JSON."
  type        = string
}

variable "ssm_secrets_parameter" {
  description = "Human-owned SSM SecureString JSON."
  type        = string
}

variable "graph_service_image" {
  description = "graph-service image used by the fetch-graph CronJob."
  type        = string
}

variable "arcadedb_bolt_uri" {
  type    = string
  default = "bolt://arcadedb.arcadedb.svc.cluster.local:7687"
}

variable "arcadedb_http_url" {
  type    = string
  default = "http://arcadedb.arcadedb.svc.cluster.local:2480"
}
