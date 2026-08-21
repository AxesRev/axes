variable "name" {
  description = "Name prefix for AWS resources."
  type        = string
}

variable "image" {
  description = "Lambda container image from ECR."
  type        = string
}

variable "private_subnet_ids" {
  type = list(string)
}

variable "db_clients_security_group_id" {
  description = "SG already allowed to reach RDS."
  type        = string
}

variable "auth0_domain" {
  type = string
}

variable "auth0_client_id" {
  type = string
}

variable "ssm_generated_parameter" {
  description = "Terraform-owned SSM SecureString JSON."
  type        = string
}

variable "tags" {
  type    = map(string)
  default = {}
}
