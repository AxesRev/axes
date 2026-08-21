module "secrets" {
  source         = "../ssm-secrets"
  parameter_name = var.ssm_secrets_parameter
}

module "generated" {
  source         = "../ssm-secrets"
  parameter_name = var.ssm_generated_parameter
}

locals {
  secrets   = module.secrets.values
  generated = module.generated.values

  from_deps = {
    APP_BASE_URL         = var.production_url
    TENANT_API_URL       = var.tenant_api_url
    BILLING_API_URL      = var.billing_api_url
    INTEGRATIONS_API_URL = var.integrations_api_url
    INTERNAL_API_SECRET  = local.generated["INTERNAL_API_SECRET"]
    AUTH0_DOMAIN         = var.auth0_domain
    AUTH0_CLIENT_ID      = var.auth0_client_id
    AUTH0_CLIENT_SECRET  = var.auth0_client_secret
    AUTH0_SECRET         = local.generated["AUTH0_SECRET"]
  }

  optional_secret_keys = [
    "NEXT_PUBLIC_PADDLE_CLIENT_TOKEN",
    "NEXT_PUBLIC_PADDLE_BASE_PRICE_ID",
  ]

  from_secrets = {
    for key in local.optional_secret_keys : key => lookup(local.secrets, key, "")
    if lookup(local.secrets, key, "") != ""
  }

  environment = sensitive(merge(local.from_deps, local.from_secrets))
}

provider "vercel" {
  api_token = local.secrets["VERCEL_API_TOKEN"]
  team      = var.team_id
}

resource "vercel_project_environment_variables" "this" {
  project_id = var.project_id
  team_id    = var.team_id

  variables = [
    for key, value in local.environment : {
      key       = key
      value     = value
      target    = ["production", "preview"]
      sensitive = true
    }
  ]
}

data "vercel_project_directory" "this" {
  path = var.source_path
}

# Project env vars do not update an existing production deployment. Pin Auth0
# (and the rest) on the deployment itself and replace it when those values change.
resource "terraform_data" "webapp_runtime" {
  triggers_replace = {
    auth0_domain         = var.auth0_domain
    auth0_client_id      = var.auth0_client_id
    production_url       = var.production_url
    tenant_api_url       = var.tenant_api_url
    billing_api_url      = var.billing_api_url
    integrations_api_url = var.integrations_api_url
  }
}

resource "vercel_deployment" "this" {
  project_id  = var.project_id
  team_id     = var.team_id
  files       = data.vercel_project_directory.this.files
  path_prefix = data.vercel_project_directory.this.path
  production  = true
  environment = local.environment

  depends_on = [vercel_project_environment_variables.this]

  lifecycle {
    replace_triggered_by = [terraform_data.webapp_runtime]
  }
}
