locals {
  password = var.password != null ? var.password : random_password.this[0].result

  mcp_config = jsonencode({
    enabled           = true
    allowReads        = true
    allowInsert       = false
    allowUpdate       = false
    allowDelete       = false
    allowSchemaChange = false
    allowAdmin        = false
    profile           = "rag"
    # Every authenticated user may call MCP; each tenant reader can only see its own database.
    allowedUsers = ["*"]
  })
}

resource "random_password" "this" {
  count = var.password == null ? 1 : 0

  length  = 24
  special = false
}

resource "random_password" "tenant_key" {
  length  = 48
  special = false
}

resource "kubernetes_namespace_v1" "this" {
  metadata {
    name = var.namespace
    labels = {
      "app.kubernetes.io/name" = "arcadedb"
    }
  }
}

resource "kubernetes_secret_v1" "auth" {
  metadata {
    name      = "arcadedb-auth"
    namespace = kubernetes_namespace_v1.this.metadata[0].name
  }

  data = sensitive({
    ARCADEDB_ROOT_PASSWORD = local.password
  })

  type = "Opaque"
}

resource "kubernetes_config_map_v1" "mcp" {
  metadata {
    name      = "arcadedb-mcp"
    namespace = kubernetes_namespace_v1.this.metadata[0].name
  }

  data = {
    "mcp-config.json" = local.mcp_config
  }
}

resource "kubernetes_storage_class_v1" "gp3" {
  count = var.create_storage_class ? 1 : 0

  metadata {
    name = var.storage_class_name
  }

  storage_provisioner    = "ebs.csi.aws.com"
  reclaim_policy         = "Delete"
  volume_binding_mode    = "WaitForFirstConsumer"
  allow_volume_expansion = true

  parameters = {
    type = "gp3"
  }
}

resource "kubernetes_stateful_set_v1" "this" {
  metadata {
    name      = "arcadedb"
    namespace = kubernetes_namespace_v1.this.metadata[0].name
    labels = {
      "app.kubernetes.io/name" = "arcadedb"
    }
  }

  wait_for_rollout = false

  spec {
    service_name = "arcadedb"
    replicas     = 1

    selector {
      match_labels = {
        "app.kubernetes.io/name" = "arcadedb"
      }
    }

    template {
      metadata {
        labels = {
          "app.kubernetes.io/name" = "arcadedb"
        }
        annotations = {
          "axes/mcp-config-sha" = sha1(local.mcp_config)
        }
      }

      spec {
        enable_service_links = false

        security_context {
          run_as_user  = 1000
          run_as_group = 1000
          fs_group     = 1000
        }

        # Users, groups and MCP settings live in config/; keep it on the volume so tenant
        # reader users survive restarts. Seed it from the image once, refresh mcp-config.json.
        init_container {
          name    = "seed-config"
          image   = var.image
          command = ["sh", "-c", "mkdir -p /data/config /data/databases && cp -rn /home/arcadedb/config/. /data/config/ && cp /mcp/mcp-config.json /data/config/mcp-config.json"]

          volume_mount {
            name       = "data"
            mount_path = "/data"
          }

          volume_mount {
            name       = "mcp"
            mount_path = "/mcp"
          }
        }

        container {
          name  = "arcadedb"
          image = var.image

          port {
            name           = "http"
            container_port = 2480
          }

          port {
            name           = "bolt"
            container_port = 7687
          }

          env {
            name = "ARCADEDB_ROOT_PASSWORD"
            value_from {
              secret_key_ref {
                name = kubernetes_secret_v1.auth.metadata[0].name
                key  = "ARCADEDB_ROOT_PASSWORD"
              }
            }
          }

          env {
            name  = "ARCADEDB_SETTINGS"
            value = "-Darcadedb.server.rootPassword=$(ARCADEDB_ROOT_PASSWORD) -Darcadedb.server.plugins=Bolt:com.arcadedb.bolt.BoltProtocolPlugin"
          }

          resources {
            requests = {
              cpu    = "100m"
              memory = "768Mi"
            }
            limits = {
              cpu    = "1"
              memory = "2Gi"
            }
          }

          readiness_probe {
            http_get {
              path = "/api/v1/ready"
              port = 2480
            }
            initial_delay_seconds = 5
            period_seconds        = 2
            timeout_seconds       = 1
            failure_threshold     = 90
          }

          liveness_probe {
            http_get {
              path = "/api/v1/ready"
              port = 2480
            }
            initial_delay_seconds = 30
            period_seconds        = 5
            timeout_seconds       = 2
            failure_threshold     = 30
          }

          volume_mount {
            name       = "data"
            mount_path = "/home/arcadedb/databases"
            sub_path   = "databases"
          }

          volume_mount {
            name       = "data"
            mount_path = "/home/arcadedb/config"
            sub_path   = "config"
          }
        }

        volume {
          name = "mcp"
          config_map {
            name = kubernetes_config_map_v1.mcp.metadata[0].name
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
        storage_class_name = var.create_storage_class ? kubernetes_storage_class_v1.gp3[0].metadata[0].name : var.storage_class_name

        resources {
          requests = {
            storage = var.storage_size
          }
        }
      }
    }
  }
}

resource "kubernetes_service_v1" "this" {
  metadata {
    name      = "arcadedb"
    namespace = kubernetes_namespace_v1.this.metadata[0].name
    labels = {
      "app.kubernetes.io/name" = "arcadedb"
    }
  }

  spec {
    selector = {
      "app.kubernetes.io/name" = "arcadedb"
    }

    port {
      name        = "http"
      port        = 2480
      target_port = 2480
    }

    port {
      name        = "bolt"
      port        = 7687
      target_port = 7687
    }

    type = "ClusterIP"
  }
}
