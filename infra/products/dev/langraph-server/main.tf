locals {
  migrate_job_name = "langraph-server-migrate-${substr(sha1(var.image), 0, 10)}"
  generated        = module.generated.values
}

module "generated" {
  source         = "../../../modules/ssm-secrets"
  parameter_name = var.ssm_generated_parameter
}

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
    POSTGRES_HOST     = local.generated["POSTGRES_HOST"]
    POSTGRES_PORT     = local.generated["POSTGRES_PORT"]
    POSTGRES_DB       = local.generated["POSTGRES_DB"]
    POSTGRES_USER     = local.generated["POSTGRES_USER"]
    POSTGRES_PASSWORD = local.generated["POSTGRES_PASSWORD"]
  }

  type = "Opaque"
}

resource "kubernetes_job_v1" "migrate" {
  metadata {
    name      = local.migrate_job_name
    namespace = kubernetes_namespace_v1.this.metadata[0].name
    labels = {
      "app.kubernetes.io/name"       = "langraph-server-migrate"
      "app.kubernetes.io/managed-by" = "terraform"
    }
  }

  wait_for_completion = true

  timeouts {
    create = "15m"
  }

  spec {
    ttl_seconds_after_finished = 600
    backoff_limit              = 2

    template {
      metadata {
        labels = {
          "app.kubernetes.io/name" = "langraph-server-migrate"
        }
      }

      spec {
        restart_policy = "Never"

        container {
          name  = "migrate"
          image = var.image

          command = ["alembic", "upgrade", "head"]

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

  depends_on = [kubernetes_secret_v1.postgres]
}

resource "kubernetes_deployment_v1" "this" {
  metadata {
    name      = "langraph-server"
    namespace = kubernetes_namespace_v1.this.metadata[0].name
    labels = {
      "app.kubernetes.io/name" = "langraph-server"
    }
  }

  depends_on = [kubernetes_job_v1.migrate]

  spec {
    replicas                  = var.replicas
    progress_deadline_seconds = 30

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
            initial_delay_seconds = 5
            period_seconds        = 5
            failure_threshold     = 5
          }

          liveness_probe {
            http_get {
              path = "/health"
              port = 8000
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
