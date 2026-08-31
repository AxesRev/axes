locals {
  job_name = "fetch-graph-${substr(replace(var.neo4j_uid, "-", ""), 0, 10)}"
  labels = {
    "app.kubernetes.io/name"      = "fetch-graph"
    "app.kubernetes.io/component" = "graph-fetch"
  }
  secret_names = [
    var.postgres_secret_name,
    var.github_secret_name,
    var.salesforce_secret_name,
    kubernetes_secret_v1.neo4j.metadata[0].name,
  ]
}

resource "kubernetes_secret_v1" "neo4j" {
  metadata {
    name      = "fetch-graph-neo4j"
    namespace = var.namespace
    labels    = local.labels
  }

  data = sensitive({
    NEO4J_USER     = "neo4j"
    NEO4J_PASSWORD = var.neo4j_password
  })

  type = "Opaque"
}

resource "kubernetes_service_account_v1" "this" {
  metadata {
    name      = "fetch-graph"
    namespace = var.namespace
    labels    = local.labels
  }

  automount_service_account_token = false
}

resource "kubernetes_job_v1" "this" {
  metadata {
    name      = local.job_name
    namespace = var.namespace
    labels    = local.labels
  }

  wait_for_completion = false

  lifecycle {
    ignore_changes = [spec]
  }

  spec {
    backoff_limit           = 3
    active_deadline_seconds = 2400

    template {
      metadata {
        labels = local.labels
      }

      spec {
        service_account_name            = kubernetes_service_account_v1.this.metadata[0].name
        automount_service_account_token = false
        restart_policy                  = "Never"
        enable_service_links            = false

        container {
          name  = "fetch-graph"
          image = var.image

          env {
            name  = "NEO4J_URI"
            value = var.bolt_uri
          }

          dynamic "env_from" {
            for_each = local.secret_names
            content {
              secret_ref {
                name = env_from.value
              }
            }
          }

          resources {
            requests = {
              cpu    = "100m"
              memory = "512Mi"
            }
            limits = {
              cpu    = "1"
              memory = "1536Mi"
            }
          }
        }
      }
    }
  }
}

resource "kubernetes_cron_job_v1" "manual" {
  metadata {
    name      = "fetch-graph"
    namespace = var.namespace
    labels    = local.labels
  }

  spec {
    schedule                      = "0 0 1 1 *"
    suspend                       = true
    concurrency_policy            = "Forbid"
    successful_jobs_history_limit = 1
    failed_jobs_history_limit     = 3

    job_template {
      metadata {
        labels = local.labels
      }

      spec {
        backoff_limit              = 3
        active_deadline_seconds    = 2400
        ttl_seconds_after_finished = 86400

        template {
          metadata {
            labels = local.labels
          }

          spec {
            service_account_name            = kubernetes_service_account_v1.this.metadata[0].name
            automount_service_account_token = false
            restart_policy                  = "Never"
            enable_service_links            = false

            container {
              name  = "fetch-graph"
              image = var.image

              env {
                name  = "NEO4J_URI"
                value = var.bolt_uri
              }

              dynamic "env_from" {
                for_each = local.secret_names
                content {
                  secret_ref {
                    name = env_from.value
                  }
                }
              }

              resources {
                requests = {
                  cpu    = "100m"
                  memory = "512Mi"
                }
                limits = {
                  cpu    = "1"
                  memory = "1536Mi"
                }
              }
            }
          }
        }
      }
    }
  }
}
