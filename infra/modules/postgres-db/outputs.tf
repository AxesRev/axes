output "name" {
  value = postgresql_database.this.name
}

output "app_username" {
  value = var.create_app_user ? local.app_username : null
}

output "app_password" {
  value     = local.app_password
  sensitive = true
}
