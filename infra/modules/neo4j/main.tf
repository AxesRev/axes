locals {
  auth        = "neo4j/${var.password}"
  storage     = "${var.size_gb}Gi"
  volume_name = "neo4j-data"
  claim_name  = "neo4j-data"
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
    NEO4J_PASSWORD = var.password
  }

  type = "Opaque"
}

resource "kubernetes_persistent_volume_v1" "this" {
  metadata {
    name = local.volume_name
  }

  spec {
    capacity = {
      storage = local.storage
    }
    access_modes                     = ["ReadWriteOnce"]
    persistent_volume_reclaim_policy = "Retain"
    storage_class_name               = ""
    volume_mode                      = "Filesystem"

    persistent_volume_source {
      csi {
        driver        = "ebs.csi.aws.com"
        volume_handle = var.volume_id
        fs_type       = "ext4"
      }
    }

    node_affinity {
      required {
        node_selector_term {
          match_expressions {
            key      = "topology.kubernetes.io/zone"
            operator = "In"
            values   = [var.availability_zone]
          }
        }
      }
    }
  }
}

resource "kubernetes_persistent_volume_claim_v1" "this" {
  metadata {
    name      = local.claim_name
    namespace = kubernetes_namespace_v1.this.metadata[0].name
  }

  spec {
    access_modes       = ["ReadWriteOnce"]
    storage_class_name = ""
    volume_name        = kubernetes_persistent_volume_v1.this.metadata[0].name

    resources {
      requests = {
        storage = local.storage
      }
    }
  }

  depends_on = [kubernetes_persistent_volume_v1.this]
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
        enable_service_links = false

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
              cpu    = "100m"
              memory = "512Mi"
            }
            limits = {
              cpu    = "1"
              memory = "1536Mi"
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

        volume {
          name = "data"

          persistent_volume_claim {
            claim_name = kubernetes_persistent_volume_claim_v1.this.metadata[0].name
          }
        }
      }
    }
  }

  depends_on = [kubernetes_persistent_volume_claim_v1.this]
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
