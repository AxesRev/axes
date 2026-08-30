output "password" {
  value     = random_password.master.result
  sensitive = true
}

output "parameter_name" {
  value = aws_ssm_parameter.master.name
}
