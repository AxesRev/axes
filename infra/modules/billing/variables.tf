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

variable "ssm_secrets_parameter" {
  description = "Existing SSM SecureString JSON. Not managed by Terraform."
  type        = string
}

variable "charge_schedule_expression" {
  description = "EventBridge schedule for monthly usage charges."
  type        = string
  default     = "cron(0 8 1 * ? *)"
}

variable "tags" {
  type    = map(string)
  default = {}
}
