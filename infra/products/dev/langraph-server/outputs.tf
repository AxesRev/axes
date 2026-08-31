output "namespace" {
  value = kubernetes_namespace_v1.this.metadata[0].name
}

output "service_name" {
  value = kubernetes_service_v1.this.metadata[0].name
}

output "http_url" {
  value = "http://${kubernetes_service_v1.this.metadata[0].name}.${kubernetes_namespace_v1.this.metadata[0].name}.svc.cluster.local:8000"
}
