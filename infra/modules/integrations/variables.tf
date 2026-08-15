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

variable "webapp_url" {
  type = string
}

variable "slack_client_id" {
  type      = string
  sensitive = true
}

variable "slack_client_secret" {
  type      = string
  sensitive = true
}

variable "github_app_slug" {
  type = string
}

variable "github_install_state_secret" {
  type      = string
  sensitive = true
}

variable "github_client_id" {
  type      = string
  sensitive = true
}

variable "github_client_secret" {
  type      = string
  sensitive = true
}

variable "github_oauth_state_secret" {
  type      = string
  sensitive = true
}

variable "salesforce_package_version_id" {
  type    = string
  default = "04tg50000008CgjAAE"
}

variable "salesforce_install_state_secret" {
  type      = string
  sensitive = true
}

variable "salesforce_client_id" {
  type      = string
  sensitive = true
}

variable "salesforce_private_key" {
  type      = string
  sensitive = true
}

variable "salesforce_login_url" {
  type    = string
  default = "https://login.salesforce.com"
}

variable "tags" {
  type    = map(string)
  default = {}
}
