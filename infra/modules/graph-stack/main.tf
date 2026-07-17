locals {
  neo4j_password = var.neo4j_password != null ? var.neo4j_password : random_password.neo4j[0].result
  neo4j_auth     = "neo4j/${local.neo4j_password}"
}

resource "random_password" "neo4j" {
  count = var.neo4j_password == null ? 1 : 0

  length  = 24
  special = false
}

resource "kubernetes_namespace_v1" "graph" {
  metadata {
    name = var.namespace
    labels = {
      "app.kubernetes.io/name" = "graph-stack"
    }
  }
}

resource "kubernetes_secret_v1" "neo4j" {
  metadata {
    name      = "neo4j-auth"
    namespace = kubernetes_namespace_v1.graph.metadata[0].name
  }

  data = {
    NEO4J_AUTH     = local.neo4j_auth
    NEO4J_USER     = "neo4j"
    NEO4J_PASSWORD = local.neo4j_password
  }

  type = "Opaque"
}

resource "kubernetes_storage_class_v1" "gp3" {
  metadata {
    name = "gp3"
  }

  storage_provisioner    = "ebs.csi.aws.com"
  reclaim_policy         = "Delete"
  volume_binding_mode    = "WaitForFirstConsumer"
  allow_volume_expansion = true

  parameters = {
    type = "gp3"
  }
}

resource "kubernetes_stateful_set_v1" "neo4j" {
  metadata {
    name      = "neo4j"
    namespace = kubernetes_namespace_v1.graph.metadata[0].name
    labels = {
      app = "neo4j"
    }
  }

  spec {
    service_name = "neo4j"
    replicas     = 1

    selector {
      match_labels = {
        app = "neo4j"
      }
    }

    template {
      metadata {
        labels = {
          app = "neo4j"
        }
      }

      spec {
        container {
          name  = "neo4j"
          image = var.neo4j_image

          port {
            name           = "http"
            container_port = 7474
          }

          port {
            name           = "bolt"
            container_port = 7687
          }

          env {
            name = "NEO4J_AUTH"
            value_from {
              secret_key_ref {
                name = kubernetes_secret_v1.neo4j.metadata[0].name
                key  = "NEO4J_AUTH"
              }
            }
          }

          env {
            name  = "NEO4J_PLUGINS"
            value = "[\"apoc\"]"
          }

          env {
            name  = "NEO4J_dbms_security_procedures_unrestricted"
            value = "apoc.*"
          }

          resources {
            requests = {
              cpu    = "250m"
              memory = "1Gi"
            }
            limits = {
              cpu    = "1"
              memory = "2Gi"
            }
          }

          readiness_probe {
            http_get {
              path = "/"
              port = 7474
            }
            initial_delay_seconds = 30
            period_seconds        = 10
          }

          liveness_probe {
            http_get {
              path = "/"
              port = 7474
            }
            initial_delay_seconds = 60
            period_seconds        = 20
          }

          volume_mount {
            name       = "data"
            mount_path = "/data"
          }
        }
      }
    }

    volume_claim_template {
      metadata {
        name = "data"
      }

      spec {
        access_modes       = ["ReadWriteOnce"]
        storage_class_name = kubernetes_storage_class_v1.gp3.metadata[0].name

        resources {
          requests = {
            storage = var.neo4j_storage_size
          }
        }
      }
    }
  }
}

resource "kubernetes_service_v1" "neo4j" {
  metadata {
    name      = "neo4j"
    namespace = kubernetes_namespace_v1.graph.metadata[0].name
    labels = {
      app = "neo4j"
    }
  }

  spec {
    selector = {
      app = "neo4j"
    }

    port {
      name        = "http"
      port        = 7474
      target_port = 7474
    }

    port {
      name        = "bolt"
      port        = 7687
      target_port = 7687
    }

    type = "ClusterIP"
  }
}

resource "kubernetes_deployment_v1" "neo4j_mcp" {
  metadata {
    name      = "neo4j-mcp"
    namespace = kubernetes_namespace_v1.graph.metadata[0].name
    labels = {
      app = "neo4j-mcp"
    }
  }

  spec {
    replicas = 1

    selector {
      match_labels = {
        app = "neo4j-mcp"
      }
    }

    template {
      metadata {
        labels = {
          app = "neo4j-mcp"
        }
      }

      spec {
        container {
          name  = "neo4j-mcp"
          image = var.neo4j_mcp_image

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
            value = "bolt://neo4j.${var.namespace}.svc.cluster.local:7687"
          }

          env {
            name = "NEO4J_USER"
            value_from {
              secret_key_ref {
                name = kubernetes_secret_v1.neo4j.metadata[0].name
                key  = "NEO4J_USER"
              }
            }
          }

          env {
            name = "NEO4J_PASSWORD"
            value_from {
              secret_key_ref {
                name = kubernetes_secret_v1.neo4j.metadata[0].name
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

  depends_on = [kubernetes_stateful_set_v1.neo4j]
}

resource "kubernetes_service_v1" "neo4j_mcp" {
  metadata {
    name      = "neo4j-mcp"
    namespace = kubernetes_namespace_v1.graph.metadata[0].name
    labels = {
      app = "neo4j-mcp"
    }
  }

  spec {
    selector = {
      app = "neo4j-mcp"
    }

    port {
      name        = "http"
      port        = 8811
      target_port = 8811
    }

    type = "ClusterIP"
  }
}

resource "kubernetes_deployment_v1" "graph_service" {
  metadata {
    name      = "graph-service"
    namespace = kubernetes_namespace_v1.graph.metadata[0].name
    labels = {
      app = "graph-service"
    }
  }

  spec {
    replicas = 1

    selector {
      match_labels = {
        app = "graph-service"
      }
    }

    template {
      metadata {
        labels = {
          app = "graph-service"
        }
      }

      spec {
        container {
          name    = "graph-service"
          image   = var.graph_service_image
          command = var.graph_service_command
          args    = var.graph_service_args

          env {
            name  = "NEO4J_MCP_HOST"
            value = "http://neo4j-mcp.${var.namespace}.svc.cluster.local:8811"
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
        }
      }
    }
  }

  depends_on = [kubernetes_deployment_v1.neo4j_mcp]
}
