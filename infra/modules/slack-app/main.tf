locals {
  app       = "slack-app"
  secrets   = module.secrets.values
  generated = module.generated.values
}

module "secrets" {
  source         = "../ssm-secrets"
  parameter_name = var.ssm_secrets_parameter
}

module "generated" {
  source         = "../ssm-secrets"
  parameter_name = var.ssm_generated_parameter
}

resource "kubernetes_namespace_v1" "this" {
  metadata {
    name = var.namespace
    labels = {
      "app.kubernetes.io/name" = local.app
    }
  }
}

resource "kubernetes_secret_v1" "this" {
  metadata {
    name      = local.app
    namespace = kubernetes_namespace_v1.this.metadata[0].name
  }

  data = sensitive({
    POSTGRES_HOST        = local.generated["POSTGRES_HOST"]
    POSTGRES_PORT        = local.generated["POSTGRES_PORT"]
    POSTGRES_DB          = local.generated["POSTGRES_DB"]
    POSTGRES_USER        = local.generated["POSTGRES_USER"]
    POSTGRES_PASSWORD    = local.generated["POSTGRES_PASSWORD"]
    SLACK_SIGNING_SECRET = local.secrets["SLACK_SIGNING_SECRET"]
    SLACK_CLIENT_ID      = local.secrets["SLACK_CLIENT_ID"]
    SLACK_CLIENT_SECRET  = local.secrets["SLACK_CLIENT_SECRET"]
    SLACK_BOT_TOKEN      = local.secrets["SLACK_BOT_TOKEN"]
    INTERNAL_API_SECRET  = local.generated["INTERNAL_API_SECRET"]
  })

  type = "Opaque"
}

resource "kubernetes_service_v1" "this" {
  metadata {
    name      = local.app
    namespace = kubernetes_namespace_v1.this.metadata[0].name
    labels = {
      "app.kubernetes.io/name" = local.app
    }
  }

  spec {
    selector = {
      "app.kubernetes.io/name" = local.app
    }

    port {
      name        = "http"
      port        = 8000
      target_port = 8000
      node_port   = var.node_port
    }

    type = "NodePort"
  }
}

resource "kubernetes_deployment_v1" "this" {
  metadata {
    name      = local.app
    namespace = kubernetes_namespace_v1.this.metadata[0].name
    labels = {
      "app.kubernetes.io/name" = local.app
    }
  }

  spec {
    replicas                  = var.replicas
    progress_deadline_seconds = 180

    selector {
      match_labels = {
        "app.kubernetes.io/name" = local.app
      }
    }

    template {
      metadata {
        labels = {
          "app.kubernetes.io/name" = local.app
        }
      }

      spec {
        enable_service_links = false

        container {
          name  = local.app
          image = var.image

          port {
            name           = "http"
            container_port = 8000
          }

          env {
            name  = "SERVER_URL"
            value = var.server_url
          }

          env {
            name  = "INTEGRATIONS_PUBLIC_URL"
            value = var.integrations_public_url
          }

          dynamic "env" {
            for_each = toset([
              "POSTGRES_HOST",
              "POSTGRES_PORT",
              "POSTGRES_DB",
              "POSTGRES_USER",
              "POSTGRES_PASSWORD",
              "SLACK_SIGNING_SECRET",
              "SLACK_CLIENT_ID",
              "SLACK_CLIENT_SECRET",
              "SLACK_BOT_TOKEN",
              "INTERNAL_API_SECRET",
            ])
            content {
              name = env.value
              value_from {
                secret_key_ref {
                  name = kubernetes_secret_v1.this.metadata[0].name
                  key  = env.value
                }
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

data "aws_region" "current" {}

resource "terraform_data" "slack_manifest" {
  input = {
    server_url       = var.server_url
    integrations_url = var.integrations_public_url
    manifest_sha     = filesha256(var.manifest_path)
  }

  depends_on = [
    kubernetes_deployment_v1.this,
    kubernetes_service_v1.this,
  ]

  provisioner "local-exec" {
    command = "python3 -u \"${replace(var.deploy_manifest_script, "\\", "/")}\""

    environment = {
      SERVER_URL              = var.server_url
      INTEGRATIONS_PUBLIC_URL = var.integrations_public_url
      SSM_SECRETS_PARAMETER   = var.ssm_secrets_parameter
      AWS_REGION              = data.aws_region.current.region
      MANIFEST_PATH           = var.manifest_path
    }
  }
}
