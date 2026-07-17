resource "kubernetes_deployment_v1" "this" {
  metadata {
    name      = "neo4j-mcp"
    namespace = var.namespace
    labels = {
      "app.kubernetes.io/name" = "neo4j-mcp"
    }
  }

  spec {
    replicas = var.replicas

    selector {
      match_labels = {
        "app.kubernetes.io/name" = "neo4j-mcp"
      }
    }

    template {
      metadata {
        labels = {
          "app.kubernetes.io/name" = "neo4j-mcp"
        }
      }

      spec {
        container {
          name  = "neo4j-mcp"
          image = var.image

          port {
            name           = "http"
            container_port = 8811
          }

          env {
            name  = "NEO4J_TRANSPORT"
            value = "http"
          }

          env {
            name  = "NEO4J_URI"
            value = var.neo4j_bolt_uri
          }

          env {
            name = "NEO4J_USER"
            value_from {
              secret_key_ref {
                name = var.auth_secret_name
                key  = "NEO4J_USER"
              }
            }
          }

          env {
            name = "NEO4J_PASSWORD"
            value_from {
              secret_key_ref {
                name = var.auth_secret_name
                key  = "NEO4J_PASSWORD"
              }
            }
          }

          env {
            name  = "NEO4J_DATABASE"
            value = "neo4j"
          }

          env {
            name  = "NEO4J_MCP_SERVER_HOST"
            value = "0.0.0.0"
          }

          env {
            name  = "NEO4J_MCP_SERVER_PORT"
            value = "8811"
          }

          env {
            name  = "NEO4J_READ_ONLY"
            value = "true"
          }

          env {
            name  = "NEO4J_MCP_SERVER_ALLOWED_HOSTS"
            value = "localhost,127.0.0.1,neo4j-mcp,neo4j-mcp.${var.namespace},neo4j-mcp.${var.namespace}.svc.cluster.local"
          }

          resources {
            requests = {
              cpu    = "100m"
              memory = "256Mi"
            }
            limits = {
              cpu    = "500m"
              memory = "512Mi"
            }
          }

          readiness_probe {
            tcp_socket {
              port = 8811
            }
            initial_delay_seconds = 10
            period_seconds        = 10
          }
        }
      }
    }
  }
}

resource "kubernetes_service_v1" "this" {
  metadata {
    name      = "neo4j-mcp"
    namespace = var.namespace
    labels = {
      "app.kubernetes.io/name" = "neo4j-mcp"
    }
  }

  spec {
    selector = {
      "app.kubernetes.io/name" = "neo4j-mcp"
    }

    port {
      name        = "http"
      port        = 8811
      target_port = 8811
    }

    type = "ClusterIP"
  }
}
