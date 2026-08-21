output "invoke_url" {
  description = "Public HTTPS URL for /app_integrations/*."
  value       = aws_apigatewayv2_api.this.api_endpoint
}

output "api_function_name" {
  value = aws_lambda_function.api.function_name
}
