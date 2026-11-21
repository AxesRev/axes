output "namespace" {
  value = kubernetes_namespace_v1.this.metadata[0].name
}

output "service_name" {
  value = kubernetes_service_v1.this.metadata[0].name
}

output "bolt_uri" {
  value = "bolt://${kubernetes_service_v1.this.metadata[0].name}.${kubernetes_namespace_v1.this.metadata[0].name}.svc.cluster.local:7687"
}

output "http_url" {
  value = "http://${kubernetes_service_v1.this.metadata[0].name}.${kubernetes_namespace_v1.this.metadata[0].name}.svc.cluster.local:2480"
}

output "auth_secret_name" {
  value = kubernetes_secret_v1.auth.metadata[0].name
}

output "password" {
  value     = local.password
  sensitive = true
}

output "tenant_key" {
  description = "HMAC key deriving each tenant's read-only ArcadeDB user password (shared by ingestion and the agent)."
  value       = random_password.tenant_key.result
  sensitive   = true
}
