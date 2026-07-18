output "namespace" {
  value = kubernetes_namespace_v1.this.metadata[0].name
}

output "service_name" {
  value = kubernetes_service_v1.this.metadata[0].name
}

output "bolt_uri" {
  value = "bolt://${kubernetes_service_v1.this.metadata[0].name}.${kubernetes_namespace_v1.this.metadata[0].name}.svc.cluster.local:7687"
}

output "auth_secret_name" {
  value = kubernetes_secret_v1.auth.metadata[0].name
}

output "password" {
  value     = var.password
  sensitive = true
}

output "volume_id" {
  value = var.volume_id
}
