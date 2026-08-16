output "parameter_name" {
  value = aws_ssm_parameter.this.name
}

output "arn" {
  value = aws_ssm_parameter.this.arn
}

output "values" {
  description = "Same map written to SSM."
  value       = var.values
  sensitive   = true
}
