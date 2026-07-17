output "name" {
  value = var.name
}

output "app_username" {
  value = var.create_app_user ? local.app_username : null
}

output "app_password" {
  value     = local.app_password
  sensitive = true
}

output "bootstrap_job_name" {
  value     = nonsensitive(kubernetes_job_v1.bootstrap.metadata[0].name)
  sensitive = false
}
