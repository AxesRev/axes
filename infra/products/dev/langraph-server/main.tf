locals {
  migrate_job_name = "langraph-server-migrate-${substr(sha1(var.image), 0, 10)}"
  generated        = module.generated.values
  secrets          = module.secrets.values
}

module "generated" {
  source         = "../../../modules/ssm-secrets"
  parameter_name = var.ssm_generated_parameter
}

module "secrets" {
  source         = "../../../modules/ssm-secrets"
  parameter_name = var.ssm_secrets_parameter
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

  data = sensitive({
    POSTGRES_HOST     = local.generated["POSTGRES_HOST"]
    POSTGRES_PORT     = local.generated["POSTGRES_PORT"]
    POSTGRES_DB       = local.generated["POSTGRES_DB"]
    POSTGRES_USER     = local.generated["POSTGRES_USER"]
    POSTGRES_PASSWORD = local.generated["POSTGRES_PASSWORD"]
  })

  type = "Opaque"
}

resource "kubernetes_secret_v1" "salesforce" {
  metadata {
    name      = "langraph-server-salesforce"
    namespace = kubernetes_namespace_v1.this.metadata[0].name
  }

  data = sensitive({
    SALESFORCE_CLIENT_ID   = local.secrets["SALESFORCE_CLIENT_ID"]
    SALESFORCE_PRIVATE_KEY = local.secrets["SALESFORCE_PRIVATE_KEY"]
    SALESFORCE_LOGIN_URL   = local.secrets["SALESFORCE_LOGIN_URL"]
  })

  type = "Opaque"
}

resource "kubernetes_secret_v1" "openai" {
  metadata {
    name      = "langraph-server-openai"
    namespace = kubernetes_namespace_v1.this.metadata[0].name
  }

  data = sensitive({
    OPENAI_API_KEY = local.secrets["OPENAI_API_KEY"]
  })

  type = "Opaque"
}

resource "kubernetes_secret_v1" "github" {
  metadata {
    name      = "langraph-server-github"
    namespace = kubernetes_namespace_v1.this.metadata[0].name
  }

  data = sensitive({
    GITHUB_APP_ID          = tostring(local.secrets["GITHUB_APP_ID"])
    GITHUB_APP_PRIVATE_KEY = local.secrets["GITHUB_APP_PRIVATE_KEY"]
  })

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

          env {
            name = "OPENAI_API_KEY"
            value_from {
              secret_key_ref {
                name = kubernetes_secret_v1.openai.metadata[0].name
                key  = "OPENAI_API_KEY"
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

  depends_on = [
    kubernetes_secret_v1.postgres,
    kubernetes_secret_v1.openai,
  ]
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
    progress_deadline_seconds = 180

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

          env {
            name = "SALESFORCE_CLIENT_ID"
            value_from {
              secret_key_ref {
                name = kubernetes_secret_v1.salesforce.metadata[0].name
                key  = "SALESFORCE_CLIENT_ID"
              }
            }
          }

          env {
            name = "SALESFORCE_PRIVATE_KEY"
            value_from {
              secret_key_ref {
                name = kubernetes_secret_v1.salesforce.metadata[0].name
                key  = "SALESFORCE_PRIVATE_KEY"
              }
            }
          }

          env {
            name = "SALESFORCE_LOGIN_URL"
            value_from {
              secret_key_ref {
                name = kubernetes_secret_v1.salesforce.metadata[0].name
                key  = "SALESFORCE_LOGIN_URL"
              }
            }
          }

          env {
            name = "OPENAI_API_KEY"
            value_from {
              secret_key_ref {
                name = kubernetes_secret_v1.openai.metadata[0].name
                key  = "OPENAI_API_KEY"
              }
            }
          }

          env {
            name = "GITHUB_APP_ID"
            value_from {
              secret_key_ref {
                name = kubernetes_secret_v1.github.metadata[0].name
                key  = "GITHUB_APP_ID"
              }
            }
          }

          env {
            name = "GITHUB_APP_PRIVATE_KEY"
            value_from {
              secret_key_ref {
                name = kubernetes_secret_v1.github.metadata[0].name
                key  = "GITHUB_APP_PRIVATE_KEY"
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
            initial_delay_seconds = 2
            period_seconds        = 2
            timeout_seconds       = 1
            failure_threshold     = 60
          }

          liveness_probe {
            http_get {
              path = "/health"
              port = 8000
            }
            initial_delay_seconds = 10
            period_seconds        = 2
            timeout_seconds       = 1
            failure_threshold     = 60
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
