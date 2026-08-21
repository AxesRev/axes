output "domain" {
  value = local.secrets["AUTH0_DOMAIN"]
}

output "client_id" {
  value = auth0_client.webapp.client_id
}

output "client_secret" {
  value     = auth0_client.webapp.client_secret
  sensitive = true
}
