resource "random_password" "internal_api_secret" {
  length  = 48
  special = false
}

resource "random_password" "auth0_secret" {
  length  = 64
  special = false
}

locals {
  values = merge(var.values, {
    INTERNAL_API_SECRET = random_password.internal_api_secret.result
    AUTH0_SECRET        = random_password.auth0_secret.result
  })
}

resource "aws_ssm_parameter" "this" {
  name        = var.parameter_name
  description = "Terraform-generated Axes env. Not human secrets."
  type        = "SecureString"
  tier        = "Advanced"
  value       = sensitive(jsonencode(local.values))
  tags        = var.tags
}
