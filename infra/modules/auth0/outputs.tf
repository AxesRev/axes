output "domain" {
  value = nonsensitive(local.secrets["AUTH0_DOMAIN"])
}

output "client_id" {
  value = auth0_client.webapp.client_id
}

output "client_secret" {
  value     = data.auth0_client.webapp.client_secret
  sensitive = true
}
