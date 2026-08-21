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
