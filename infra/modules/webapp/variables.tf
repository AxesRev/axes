variable "name" {
  description = "Vercel project name and *.vercel.app subdomain. Must be unique on Vercel."
  type        = string
}

variable "team_id" {
  description = "Vercel team ID (team_...)."
  type        = string
}

variable "root_directory" {
  description = "Path to the Next.js app inside the git repo."
  type        = string
  default     = "webapp/axes"
}

variable "ssm_secrets_parameter" {
  description = "Existing SSM SecureString JSON. Must contain VERCEL_API_TOKEN."
  type        = string
}

variable "tags" {
  type    = map(string)
  default = {}
}
