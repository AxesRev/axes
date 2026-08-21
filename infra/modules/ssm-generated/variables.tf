variable "parameter_name" {
  description = "SSM SecureString JSON owned by Terraform."
  type        = string
}

variable "values" {
  description = "Env keys Terraform generated. All values must be strings."
  type        = map(string)
  sensitive   = true
}

variable "tags" {
  type    = map(string)
  default = {}
}
