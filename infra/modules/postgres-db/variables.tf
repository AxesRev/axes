variable "name" {
  description = "Name of the PostgreSQL database to create."
  type        = string
}

variable "host" {
  description = "RDS hostname."
  type        = string
}

variable "port" {
  description = "RDS port."
  type        = number
  default     = 5432
}

variable "master_username" {
  description = "RDS master username used by the bootstrap Job."
  type        = string
}

variable "master_password" {
  description = "RDS master password used by the bootstrap Job."
  type        = string
  sensitive   = true
}

variable "namespace" {
  description = "Kubernetes namespace for the bootstrap Job."
  type        = string
  default     = "kube-system"
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

variable "postgres_image" {
  description = "Image with psql used for bootstrap."
  type        = string
  default     = "public.ecr.aws/docker/library/postgres:16-alpine"
}
