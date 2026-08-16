resource "aws_ssm_parameter" "this" {
  name        = var.parameter_name
  description = "Terraform-generated Axes env. Not human secrets."
  type        = "SecureString"
  tier        = "Advanced"
  value       = jsonencode(var.values)
  tags        = var.tags
}
