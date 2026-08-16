data "aws_ssm_parameter" "this" {
  name            = var.parameter_name
  with_decryption = true
}

locals {
  values = sensitive(jsondecode(data.aws_ssm_parameter.this.value))
}
