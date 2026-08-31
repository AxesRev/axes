output "namespace" {
  value = kubernetes_namespace_v1.this.metadata[0].name
}

output "service_name" {
  value = kubernetes_service_v1.this.metadata[0].name
}

output "http_url" {
  value = "http://${kubernetes_service_v1.this.metadata[0].name}.${kubernetes_namespace_v1.this.metadata[0].name}.svc.cluster.local:8000"
}

output "postgres_secret_name" {
  value = kubernetes_secret_v1.postgres.metadata[0].name
}

output "github_secret_name" {
  value = kubernetes_secret_v1.github.metadata[0].name
}

output "salesforce_secret_name" {
  value = kubernetes_secret_v1.salesforce.metadata[0].name
}
