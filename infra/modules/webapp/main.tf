module "secrets" {
  source         = "../ssm-secrets"
  parameter_name = var.ssm_secrets_parameter
}

locals {
  secrets = module.secrets.values
}

provider "vercel" {
  api_token = local.secrets["VERCEL_API_TOKEN"]
  team      = var.team_id
}

resource "vercel_project" "this" {
  name         = var.name
  framework    = "nextjs"
  node_version = "22.x"
  team_id      = var.team_id
}
