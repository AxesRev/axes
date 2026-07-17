variable "name" {
  description = "Name of the PostgreSQL database to create."
  type        = string
}

variable "owner" {
  description = "Database owner role. Defaults to the connecting (master) role when null."
  type        = string
  default     = null
}

variable "create_app_user" {
  description = "Create a dedicated app role with CONNECT/USAGE grants on this database."
  type        = bool
  default     = true
}

variable "app_username" {
  description = "App role name. Defaults to \"{name}_app\" when create_app_user is true."
  type        = string
  default     = null
}

variable "app_password" {
  description = "App role password. Generated when null and create_app_user is true."
  type        = string
  default     = null
  sensitive   = true
}

variable "extensions" {
  description = "PostgreSQL extensions to enable in this database (e.g. vector)."
  type        = list(string)
  default     = []
}
