output "namespace" {
  value = kubernetes_namespace_v1.this.metadata[0].name
}

output "invoke_url" {
  description = "Public HTTPS URL for Slack request URLs."
  value       = aws_apigatewayv2_api.this.api_endpoint
}
