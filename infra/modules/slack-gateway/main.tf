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
