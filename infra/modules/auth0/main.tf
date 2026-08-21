module "secrets" {
  source         = "../ssm-secrets"
  parameter_name = var.ssm_secrets_parameter
}

locals {
  secrets = module.secrets.values
  origin  = trimsuffix(var.production_url, "/")
}

provider "auth0" {
  domain        = local.secrets["AUTH0_DOMAIN"]
  client_id     = local.secrets["AUTH0_MGMT_CLIENT_ID"]
  client_secret = local.secrets["AUTH0_MGMT_CLIENT_SECRET"]
}

resource "auth0_client" "webapp" {
  name                = var.name
  app_type            = "regular_web"
  oidc_conformant     = true
  is_first_party      = true
  callbacks           = ["${local.origin}/api/auth/callback", "http://localhost:3000/api/auth/callback"]
  allowed_logout_urls = [local.origin, "http://localhost:3000"]
  web_origins         = [local.origin, "http://localhost:3000"]
  grant_types         = ["authorization_code", "refresh_token"]

  jwt_configuration {
    alg = "RS256"
  }
}

data "auth0_connection" "database" {
  name = "Username-Password-Authentication"
}

resource "auth0_connection_client" "database" {
  connection_id = data.auth0_connection.database.id
  client_id     = auth0_client.webapp.id
}

data "auth0_client" "webapp" {
  client_id = auth0_client.webapp.id
}

import {
  to = auth0_client.webapp
  id = "Mgoww0WHHTlxXF0BtMwVDTjveNgMKqAB"
}
