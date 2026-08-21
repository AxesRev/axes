output "parameter_name" {
  value = aws_ssm_parameter.this.name
}

output "arn" {
  value = aws_ssm_parameter.this.arn
}

output "values" {
  description = "Same map written to SSM."
  value       = local.values
  sensitive   = true
}
