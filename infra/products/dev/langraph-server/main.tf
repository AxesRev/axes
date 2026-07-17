resource "kubernetes_namespace_v1" "this" {
  metadata {
    name = var.namespace
    labels = {
      "app.kubernetes.io/name" = "langraph-server"
    }
  }
}

resource "kubernetes_secret_v1" "postgres" {
  metadata {
    name      = "langraph-server-postgres"
    namespace = kubernetes_namespace_v1.this.metadata[0].name
  }

  data = {
    POSTGRES_HOST     = var.postgres_host
    POSTGRES_PORT     = tostring(var.postgres_port)
    POSTGRES_DB       = var.postgres_db
    POSTGRES_USER     = var.postgres_user
    POSTGRES_PASSWORD = var.postgres_password
  }

  type = "Opaque"
}

resource "kubernetes_deployment_v1" "this" {
  metadata {
    name      = "langraph-server"
    namespace = kubernetes_namespace_v1.this.metadata[0].name
    labels = {
      "app.kubernetes.io/name" = "langraph-server"
    }
  }

  spec {
    replicas = var.replicas

    selector {
      match_labels = {
        "app.kubernetes.io/name" = "langraph-server"
      }
    }

    template {
      metadata {
        labels = {
          "app.kubernetes.io/name" = "langraph-server"
        }
      }

      spec {
        container {
          name  = "langraph-server"
          image = var.image

          port {
            name           = "http"
            container_port = 8000
          }

          env {
            name  = "HOST"
            value = "0.0.0.0"
          }

          env {
            name  = "PORT"
            value = "8000"
          }

          env {
            name  = "AUTH_TYPE"
            value = var.auth_type
          }

          env {
            name  = "AEGRA_CONFIG"
            value = "aegra.json"
          }

          env {
            name = "POSTGRES_HOST"
            value_from {
              secret_key_ref {
                name = kubernetes_secret_v1.postgres.metadata[0].name
                key  = "POSTGRES_HOST"
              }
            }
          }

          env {
            name = "POSTGRES_PORT"
            value_from {
              secret_key_ref {
                name = kubernetes_secret_v1.postgres.metadata[0].name
                key  = "POSTGRES_PORT"
              }
            }
          }

          env {
            name = "POSTGRES_DB"
            value_from {
              secret_key_ref {
                name = kubernetes_secret_v1.postgres.metadata[0].name
                key  = "POSTGRES_DB"
              }
            }
          }

          env {
            name = "POSTGRES_USER"
            value_from {
              secret_key_ref {
                name = kubernetes_secret_v1.postgres.metadata[0].name
                key  = "POSTGRES_USER"
              }
            }
          }

          env {
            name = "POSTGRES_PASSWORD"
            value_from {
              secret_key_ref {
                name = kubernetes_secret_v1.postgres.metadata[0].name
                key  = "POSTGRES_PASSWORD"
              }
            }
          }

          dynamic "env" {
            for_each = var.neo4j_mcp_host != "" ? [1] : []
            content {
              name  = "NEO4J_MCP_HOST"
              value = var.neo4j_mcp_host
            }
          }

          resources {
            requests = {
              cpu    = "250m"
              memory = "512Mi"
            }
            limits = {
              cpu    = "1"
              memory = "1Gi"
            }
          }

          readiness_probe {
            http_get {
              path = "/health"
              port = 8000
            }
            initial_delay_seconds = 20
            period_seconds        = 10
          }

          liveness_probe {
            http_get {
              path = "/health"
              port = 8000
            }
            initial_delay_seconds = 40
            period_seconds        = 20
          }
        }
      }
    }
  }
}

resource "kubernetes_service_v1" "this" {
  metadata {
    name      = "langraph-server"
    namespace = kubernetes_namespace_v1.this.metadata[0].name
    labels = {
      "app.kubernetes.io/name" = "langraph-server"
    }
  }

  spec {
    selector = {
      "app.kubernetes.io/name" = "langraph-server"
    }

    port {
      name        = "http"
      port        = 8000
      target_port = 8000
    }

    type = "ClusterIP"
  }
}
