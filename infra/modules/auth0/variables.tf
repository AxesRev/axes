variable "name" {
  description = "Auth0 application name."
  type        = string
}

variable "production_url" {
  description = "Public webapp origin used for Auth0 callbacks and logout URLs."
  type        = string
}

variable "ssm_secrets_parameter" {
  description = "Existing SSM SecureString JSON. Must contain AUTH0_DOMAIN, AUTH0_MGMT_CLIENT_ID, AUTH0_MGMT_CLIENT_SECRET."
  type        = string
}

variable "tags" {
  type    = map(string)
  default = {}
}
