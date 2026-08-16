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
  secrets    = module.secrets.values
  generated  = module.generated.values
  environment = sensitive({
    POSTGRES_HOST           = local.generated["POSTGRES_HOST"]
    POSTGRES_PORT           = local.generated["POSTGRES_PORT"]
    POSTGRES_DB             = local.generated["POSTGRES_DB"]
    POSTGRES_USER           = local.generated["POSTGRES_USER"]
    POSTGRES_PASSWORD       = local.generated["POSTGRES_PASSWORD"]
    AUTH0_DOMAIN            = local.secrets["AUTH0_DOMAIN"]
    AUTH0_CLIENT_ID         = local.secrets["AUTH0_CLIENT_ID"]
  })
}

module "secrets" {
  source         = "../ssm-secrets"
  parameter_name = var.ssm_secrets_parameter
}

module "generated" {
  source         = "../ssm-secrets"
  parameter_name = var.ssm_generated_parameter
}

resource "aws_cloudwatch_log_group" "api" {
  name              = "/aws/lambda/${var.name}-api"
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
    command = ["tenants.app.handler"]
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

resource "aws_apigatewayv2_route" "tenants_me" {
  api_id    = aws_apigatewayv2_api.this.id
  route_key = "ANY /tenants/me"
  target    = "integrations/${aws_apigatewayv2_integration.this.id}"
}

resource "aws_apigatewayv2_route" "tenants" {
  api_id    = aws_apigatewayv2_api.this.id
  route_key = "ANY /tenants/{proxy+}"
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
