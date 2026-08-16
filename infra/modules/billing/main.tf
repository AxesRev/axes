data "aws_iam_policy_document" "assume" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "this" {
  name               = var.name
  assume_role_policy = data.aws_iam_policy_document.assume.json
  tags               = var.tags
}

resource "aws_iam_role_policy_attachment" "logs" {
  role       = aws_iam_role.this.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy_attachment" "vpc" {
  role       = aws_iam_role.this.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}

locals {
  secrets = module.secrets.values
  environment = {
    POSTGRES_HOST           = var.postgres_host
    POSTGRES_PORT           = tostring(var.postgres_port)
    POSTGRES_DB             = var.postgres_db
    POSTGRES_USER           = var.postgres_user
    POSTGRES_PASSWORD       = var.postgres_password
    INTERNAL_API_SECRET     = local.secrets["INTERNAL_API_SECRET"]
    PADDLE_API_KEY          = local.secrets["PADDLE_API_KEY"]
    PADDLE_WEBHOOK_SECRET   = local.secrets["PADDLE_WEBHOOK_SECRET"]
    PADDLE_USAGE_PRICE_ID   = local.secrets["PADDLE_USAGE_PRICE_ID"]
  }
}

module "secrets" {
  source         = "../ssm-secrets"
  parameter_name = var.ssm_secrets_parameter
}

resource "aws_cloudwatch_log_group" "api" {
  name              = "/aws/lambda/${var.name}-api"
  retention_in_days = 7
  tags              = var.tags
}

resource "aws_cloudwatch_log_group" "charge" {
  name              = "/aws/lambda/${var.name}-charge"
  retention_in_days = 7
  tags              = var.tags
}

resource "aws_lambda_function" "api" {
  function_name = "${var.name}-api"
  role          = aws_iam_role.this.arn
  package_type  = "Image"
  image_uri     = var.image
  architectures = ["arm64"]
  timeout       = 15
  memory_size   = 512

  image_config {
    command = ["billing.app.handler"]
  }

  vpc_config {
    subnet_ids         = var.private_subnet_ids
    security_group_ids = [var.db_clients_security_group_id]
  }

  environment {
    variables = local.environment
  }

  depends_on = [aws_cloudwatch_log_group.api]
  tags       = var.tags
}

resource "aws_lambda_function" "charge" {
  function_name = "${var.name}-charge"
  role          = aws_iam_role.this.arn
  package_type  = "Image"
  image_uri     = var.image
  architectures = ["arm64"]
  timeout       = 300
  memory_size   = 512

  image_config {
    command = ["billing.charge_usage.handler"]
  }

  vpc_config {
    subnet_ids         = var.private_subnet_ids
    security_group_ids = [var.db_clients_security_group_id]
  }

  environment {
    variables = local.environment
  }

  depends_on = [aws_cloudwatch_log_group.charge]
  tags       = var.tags
}

resource "aws_apigatewayv2_api" "this" {
  name          = var.name
  protocol_type = "HTTP"
  tags          = var.tags
}

resource "aws_apigatewayv2_integration" "this" {
  api_id                 = aws_apigatewayv2_api.this.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.api.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "billing" {
  api_id    = aws_apigatewayv2_api.this.id
  route_key = "ANY /billing/{proxy+}"
  target    = "integrations/${aws_apigatewayv2_integration.this.id}"
}

resource "aws_apigatewayv2_route" "health" {
  api_id    = aws_apigatewayv2_api.this.id
  route_key = "GET /health"
  target    = "integrations/${aws_apigatewayv2_integration.this.id}"
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.this.id
  name        = "$default"
  auto_deploy = true
  tags        = var.tags
}

resource "aws_lambda_permission" "apigw" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.api.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.this.execution_arn}/*/*"
}

resource "aws_cloudwatch_event_rule" "charge" {
  name                = "${var.name}-charge"
  schedule_expression = var.charge_schedule_expression
  tags                = var.tags
}

resource "aws_cloudwatch_event_target" "charge" {
  rule = aws_cloudwatch_event_rule.charge.name
  arn  = aws_lambda_function.charge.arn
}

resource "aws_lambda_permission" "charge" {
  statement_id  = "AllowEventBridgeInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.charge.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.charge.arn
}
