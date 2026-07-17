output "namespace" {
  value = kubernetes_namespace_v1.graph.metadata[0].name
}

output "neo4j_service" {
  value = "${kubernetes_service_v1.neo4j.metadata[0].name}.${var.namespace}.svc.cluster.local"
}

output "neo4j_mcp_service" {
  value = "${kubernetes_service_v1.neo4j_mcp.metadata[0].name}.${var.namespace}.svc.cluster.local:8811"
}

output "neo4j_password" {
  value     = local.neo4j_password
  sensitive = true
}
