variable "project_id" {
  type = string
}

variable "team_id" {
  type = string
}

variable "production_url" {
  description = "Public webapp origin from the webapp stack output."
  type        = string
}

variable "tenant_api_url" {
  type = string
}

variable "billing_api_url" {
  type = string
}

variable "integrations_api_url" {
  type = string
}

variable "ssm_secrets_parameter" {
  description = "Existing SSM SecureString JSON. Must contain VERCEL_API_TOKEN."
  type        = string
}

variable "tags" {
  type    = map(string)
  default = {}
}
