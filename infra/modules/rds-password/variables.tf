variable "parameter_name" {
  description = "SSM SecureString that holds the RDS master password."
  type        = string
}

variable "tags" {
  type    = map(string)
  default = {}
}
