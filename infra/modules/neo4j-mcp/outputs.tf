output "service_name" {
  value = kubernetes_service_v1.this.metadata[0].name
}

output "http_url" {
  value = "http://${kubernetes_service_v1.this.metadata[0].name}.${var.namespace}.svc.cluster.local:8811"
}
