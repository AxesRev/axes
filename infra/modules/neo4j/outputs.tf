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

output "statefulset_uid" {
  description = "UID of the Neo4j StatefulSet. Changes when Neo4j is recreated; graph-fetch uses it to run once per cluster."
  value       = kubernetes_stateful_set_v1.this.metadata[0].uid
}

output "password" {
  value     = local.password
  sensitive = true
}
