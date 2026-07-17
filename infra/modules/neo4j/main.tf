locals {
  password = var.password != null ? var.password : random_password.this[0].result
  auth     = "neo4j/${local.password}"
}

resource "random_password" "this" {
  count = var.password == null ? 1 : 0

  length  = 24
  special = false
}

resource "kubernetes_namespace_v1" "this" {
  metadata {
    name = var.namespace
    labels = {
      "app.kubernetes.io/name" = "neo4j"
    }
  }
}

resource "kubernetes_secret_v1" "auth" {
  metadata {
    name      = "neo4j-auth"
    namespace = kubernetes_namespace_v1.this.metadata[0].name
  }

  data = {
    NEO4J_AUTH     = local.auth
    NEO4J_USER     = "neo4j"
    NEO4J_PASSWORD = local.password
  }

  type = "Opaque"
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
    name      = "neo4j"
    namespace = kubernetes_namespace_v1.this.metadata[0].name
    labels = {
      "app.kubernetes.io/name" = "neo4j"
    }
  }

  wait_for_rollout = false

  spec {
    service_name = "neo4j"
    replicas     = 1

    selector {
      match_labels = {
        "app.kubernetes.io/name" = "neo4j"
      }
    }

    template {
      metadata {
        labels = {
          "app.kubernetes.io/name" = "neo4j"
        }
      }

      spec {
        container {
          name  = "neo4j"
          image = var.image

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
                name = kubernetes_secret_v1.auth.metadata[0].name
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
    name      = "neo4j"
    namespace = kubernetes_namespace_v1.this.metadata[0].name
    labels = {
      "app.kubernetes.io/name" = "neo4j"
    }
  }

  spec {
    selector = {
      "app.kubernetes.io/name" = "neo4j"
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
