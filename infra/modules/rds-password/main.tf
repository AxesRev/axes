resource "random_password" "master" {
  length  = 32
  special = false
}

resource "aws_ssm_parameter" "master" {
  name        = var.parameter_name
  description = "RDS master password. Survives stack destroy; RDS is recreated with this value."
  type        = "SecureString"
  value       = random_password.master.result
  tags        = var.tags
}
