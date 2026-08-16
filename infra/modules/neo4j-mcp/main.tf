resource "kubernetes_deployment_v1" "this" {
  metadata {
    name      = "neo4j-mcp"
    namespace = var.namespace
    labels = {
      "app.kubernetes.io/name" = "neo4j-mcp"
    }
  }

  spec {
    replicas                  = var.replicas
    progress_deadline_seconds = 30

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
        enable_service_links = false

        affinity {
          pod_affinity {
            required_during_scheduling_ignored_during_execution {
              label_selector {
                match_labels = {
                  "app.kubernetes.io/name" = "neo4j"
                }
              }
              namespaces   = [var.namespace]
              topology_key = "kubernetes.io/hostname"
            }
          }
        }

        container {
          name  = "neo4j-mcp"
          image = var.image

          port {
            name           = "http"
            container_port = 8811
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
            http_get {
              path = "/health"
              port = 8811

              http_header {
                name  = "Host"
                value = "neo4j-mcp"
              }
            }
            initial_delay_seconds = 5
            period_seconds        = 5
            failure_threshold     = 5
          }

          liveness_probe {
            http_get {
              path = "/health"
              port = 8811

              http_header {
                name  = "Host"
                value = "neo4j-mcp"
              }
            }
            initial_delay_seconds = 30
            period_seconds        = 20
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
