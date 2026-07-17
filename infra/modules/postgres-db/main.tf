locals {
  app_username = var.app_username != null ? var.app_username : "${var.name}_app"
  app_password = (
    var.create_app_user
    ? (var.app_password != null ? var.app_password : random_password.app[0].result)
    : null
  )

  script_checksum = sha1(join("|", [
    var.host,
    tostring(var.port),
    var.name,
    var.master_username,
    var.master_password,
    tostring(var.create_app_user),
    local.app_username == null ? "" : local.app_username,
    local.app_password == null ? "" : local.app_password,
    join(",", var.extensions),
  ]))

  job_name = "postgres-db-${substr(local.script_checksum, 0, 10)}"
}

resource "random_password" "app" {
  count = var.create_app_user && var.app_password == null ? 1 : 0

  length  = 32
  special = false
}

resource "kubernetes_secret_v1" "bootstrap" {
  metadata {
    name      = local.job_name
    namespace = var.namespace
    labels = {
      "app.kubernetes.io/name"       = "postgres-db-bootstrap"
      "app.kubernetes.io/managed-by" = "terraform"
    }
  }

  data = {
    MASTER_PASSWORD = var.master_password
    APP_PASSWORD    = local.app_password == null ? "" : local.app_password
  }
}

resource "kubernetes_job_v1" "bootstrap" {
  metadata {
    name      = local.job_name
    namespace = var.namespace
    labels = {
      "app.kubernetes.io/name"       = "postgres-db-bootstrap"
      "app.kubernetes.io/managed-by" = "terraform"
    }
  }

  wait_for_completion = true

  timeouts {
    create = "15m"
  }

  spec {
    ttl_seconds_after_finished = 600
    backoff_limit              = 6

    template {
      metadata {
        labels = {
          "app.kubernetes.io/name" = "postgres-db-bootstrap"
        }
      }

      spec {
        restart_policy = "OnFailure"

        container {
          name  = "bootstrap"
          image = var.postgres_image

          env {
            name  = "PGHOST"
            value = var.host
          }
          env {
            name  = "PGPORT"
            value = tostring(var.port)
          }
          env {
            name  = "PGUSER"
            value = var.master_username
          }
          env {
            name  = "APP_DB"
            value = var.name
          }
          env {
            name  = "APP_USER"
            value = local.app_username == null ? "" : local.app_username
          }
          env {
            name  = "CREATE_APP_USER"
            value = var.create_app_user ? "true" : "false"
          }
          env {
            name  = "EXTENSIONS"
            value = join(" ", var.extensions)
          }
          env {
            name  = "PGSSLMODE"
            value = "require"
          }
          env {
            name = "PGPASSWORD"
            value_from {
              secret_key_ref {
                name = kubernetes_secret_v1.bootstrap.metadata[0].name
                key  = "MASTER_PASSWORD"
              }
            }
          }
          env {
            name = "APP_PASSWORD"
            value_from {
              secret_key_ref {
                name = kubernetes_secret_v1.bootstrap.metadata[0].name
                key  = "APP_PASSWORD"
              }
            }
          }

          command = ["/bin/sh", "-ec"]
          # Shell vars use $${...} so Terraform leaves ${...} for the container.
          args = [
            <<-EOF
            set -eu
            if [ "$(psql -d postgres -Atc "SELECT 1 FROM pg_database WHERE datname='$${APP_DB}'")" != "1" ]; then
              psql -d postgres -c "CREATE DATABASE \"$${APP_DB}\""
            fi

            if [ "$${CREATE_APP_USER}" = "true" ]; then
              if [ "$(psql -d postgres -Atc "SELECT 1 FROM pg_roles WHERE rolname='$${APP_USER}'")" != "1" ]; then
                psql -d postgres -c "CREATE ROLE \"$${APP_USER}\" LOGIN PASSWORD '$${APP_PASSWORD}'"
              else
                psql -d postgres -c "ALTER ROLE \"$${APP_USER}\" WITH LOGIN PASSWORD '$${APP_PASSWORD}'"
              fi
              psql -d postgres -c "GRANT CONNECT, TEMPORARY ON DATABASE \"$${APP_DB}\" TO \"$${APP_USER}\""
              psql -d "$${APP_DB}" -c "GRANT USAGE, CREATE ON SCHEMA public TO \"$${APP_USER}\""
              psql -d "$${APP_DB}" -c "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON TABLES TO \"$${APP_USER}\""
              psql -d "$${APP_DB}" -c "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO \"$${APP_USER}\""
            fi

            for ext in $${EXTENSIONS}; do
              psql -d "$${APP_DB}" -c "CREATE EXTENSION IF NOT EXISTS \"$${ext}\""
            done
            EOF
          ]
        }
      }
    }
  }

  depends_on = [kubernetes_secret_v1.bootstrap]
}
