locals {
  app = "slack-app"
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

  data = {
    POSTGRES_HOST        = var.postgres_host
    POSTGRES_PORT        = tostring(var.postgres_port)
    POSTGRES_DB          = var.postgres_db
    POSTGRES_USER        = var.postgres_user
    POSTGRES_PASSWORD    = var.postgres_password
    POSTGRES_SSLMODE     = "require"
    SLACK_SIGNING_SECRET = var.slack_signing_secret
    SLACK_CLIENT_ID      = var.slack_client_id
    SLACK_CLIENT_SECRET  = var.slack_client_secret
    SLACK_BOT_TOKEN      = var.slack_bot_token
    INTERNAL_API_SECRET  = var.internal_api_secret
  }

  type = "Opaque"
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
    progress_deadline_seconds = 30

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
            name  = "HOST"
            value = "0.0.0.0"
          }

          env {
            name  = "PORT"
            value = "8000"
          }

          env {
            name  = "SERVER_URL"
            value = aws_apigatewayv2_api.this.api_endpoint
          }

          env {
            name  = "LANGGRAPH_API_URL"
            value = var.langraph_api_url
          }

          dynamic "env" {
            for_each = toset([
              "POSTGRES_HOST",
              "POSTGRES_PORT",
              "POSTGRES_DB",
              "POSTGRES_USER",
              "POSTGRES_PASSWORD",
              "POSTGRES_SSLMODE",
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

resource "aws_security_group" "vpclink" {
  name        = "${var.name}-vpclink"
  description = "API Gateway VPC Link for ${var.name}"
  vpc_id      = var.vpc_id
  tags        = merge(var.tags, { Name = "${var.name}-vpclink" })
}

resource "aws_vpc_security_group_egress_rule" "vpclink_nlb" {
  security_group_id = aws_security_group.vpclink.id
  cidr_ipv4         = var.vpc_cidr
  from_port         = 80
  to_port           = 80
  ip_protocol       = "tcp"
}

resource "aws_vpc_security_group_ingress_rule" "nodeport" {
  security_group_id = var.node_security_group_id
  cidr_ipv4         = var.vpc_cidr
  from_port         = var.node_port
  to_port           = var.node_port
  ip_protocol       = "tcp"
  description       = "${var.name} NLB NodePort"
}

resource "aws_lb" "this" {
  name                             = var.name
  load_balancer_type               = "network"
  internal                         = true
  subnets                          = var.private_subnet_ids
  enable_cross_zone_load_balancing = true
  tags                             = var.tags
}

resource "aws_lb_target_group" "this" {
  name        = var.name
  port        = var.node_port
  protocol    = "TCP"
  vpc_id      = var.vpc_id
  target_type = "instance"
  tags        = var.tags

  health_check {
    protocol = "TCP"
    port     = "traffic-port"
  }
}

resource "aws_lb_listener" "this" {
  load_balancer_arn = aws_lb.this.arn
  port              = 80
  protocol          = "TCP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.this.arn
  }
}

resource "aws_autoscaling_attachment" "this" {
  for_each = toset(var.node_autoscaling_group_names)

  autoscaling_group_name = each.value
  lb_target_group_arn    = aws_lb_target_group.this.arn
}

resource "aws_apigatewayv2_vpc_link" "this" {
  name               = var.name
  security_group_ids = [aws_security_group.vpclink.id]
  subnet_ids         = var.private_subnet_ids
  tags               = var.tags
}

resource "aws_apigatewayv2_api" "this" {
  name          = var.name
  protocol_type = "HTTP"
  tags          = var.tags
}

resource "aws_apigatewayv2_integration" "this" {
  api_id             = aws_apigatewayv2_api.this.id
  integration_type   = "HTTP_PROXY"
  integration_method = "ANY"
  connection_type    = "VPC_LINK"
  connection_id      = aws_apigatewayv2_vpc_link.this.id
  integration_uri    = aws_lb_listener.this.arn
}

resource "aws_apigatewayv2_route" "proxy" {
  api_id    = aws_apigatewayv2_api.this.id
  route_key = "ANY /{proxy+}"
  target    = "integrations/${aws_apigatewayv2_integration.this.id}"
}

resource "aws_apigatewayv2_route" "root" {
  api_id    = aws_apigatewayv2_api.this.id
  route_key = "ANY /"
  target    = "integrations/${aws_apigatewayv2_integration.this.id}"
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.this.id
  name        = "$default"
  auto_deploy = true
  tags        = var.tags
}
