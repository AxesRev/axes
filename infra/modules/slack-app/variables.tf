variable "name" {
  description = "Name prefix for AWS resources."
  type        = string
}

variable "vpc_id" {
  type = string
}

variable "vpc_cidr" {
  type = string
}

variable "private_subnet_ids" {
  type = list(string)
}

variable "node_security_group_id" {
  description = "EKS node SG; ingress opened for the NLB NodePort."
  type        = string
}

variable "node_autoscaling_group_names" {
  description = "EKS managed node group ASG names for NLB instance targets."
  type        = list(string)
}

variable "namespace" {
  type    = string
  default = "slack-app"
}

variable "image" {
  description = "Container image from ECR."
  type        = string
}

variable "node_port" {
  description = "Static NodePort the internal NLB forwards to."
  type        = number
  default     = 30800
}

variable "replicas" {
  type    = number
  default = 1
}

variable "langraph_api_url" {
  description = "In-cluster langraph-server URL."
  type        = string
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

variable "slack_signing_secret" {
  type      = string
  sensitive = true
}

variable "slack_client_id" {
  type      = string
  sensitive = true
}

variable "slack_client_secret" {
  type      = string
  sensitive = true
}

variable "slack_bot_token" {
  type      = string
  sensitive = true
  default   = ""
}

variable "internal_api_secret" {
  description = "Shared secret for POST /internal/tenants/resolve."
  type        = string
  sensitive   = true
}

variable "tags" {
  type    = map(string)
  default = {}
}
