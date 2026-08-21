output "name" {
  description = "Vercel project name (also the *.vercel.app subdomain)."
  value       = vercel_project.this.name
}

output "project_id" {
  value = vercel_project.this.id
}

output "team_id" {
  value = var.team_id
}

output "production_url" {
  description = "Stable HTTPS origin reserved by the project name."
  value       = "https://${vercel_project.this.name}.vercel.app"
}
